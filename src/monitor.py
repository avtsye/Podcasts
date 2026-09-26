import hashlib
import json
import mimetypes
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

from src.drive import upload_audio
from src.yemos import upload_audio as upload_yemos_audio
from src.github_notify import queue_notification, flush_notifications
from src.state import load_state, save_state
from src.yemos_state import load_yemos_state, save_yemos_state, next_yemos_number

CONFIG_PATH = Path("config/podcasts.json")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def episode_key(entry):
    value = (entry.get("id") or entry.get("guid") or "").strip()
    if value:
        return value
    fallback = enclosure_url(entry) or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def enclosure_url(entry):
    for enclosure in entry.get("enclosures") or []:
        url = enclosure.get("href") or enclosure.get("url")
        if url:
            return url
    for item in entry.get("media_content") or []:
        if item.get("url"):
            return item["url"]
    return None


def safe_filename(title, url):
    suffix = Path(urlparse(url).path).suffix.lower()
    if not suffix or len(suffix) > 8:
        suffix = mimetypes.guess_extension(
            mimetypes.guess_type(url)[0] or ""
        ) or ".mp3"
    name = re.sub(r'[\\/:*?"<>|]+', "_", title).strip() or "episode"
    name = re.sub(r"\s+", " ", name)
    return name[:180] + suffix


def download(url, target, timeout):
    with requests.get(
        url,
        stream=True,
        timeout=(30, timeout),
        headers={"User-Agent": "Podcasts-RSS-Monitor/1.0"},
    ) as response:
        response.raise_for_status()
        with open(target, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)


def notify_existing_uploaded(podcast, record, notifications):
    if not notifications.get("enabled", True):
        return False

    try:
        queue_notification(
            podcast,
            record,
            {
                "id": record.get("drive_file_id"),
                "webViewLink": record.get("drive_url", ""),
            },
        )
        record["notification_status"] = "queued"
        record.pop("notification_error", None)
        return True
    except Exception as exc:
        record["notification_status"] = "error"
        record["notification_error"] = str(exc)
        print(f"WARNING: notification failed for {record.get('title')}: {exc}")
        return False


def process_feed(podcast, config, state, yemos_state):
    settings = config.get("settings", {})
    notifications = config.get("notifications", {})
    podcast_id = podcast["id"]

    print(f"Checking: {podcast['name']}")
    feed = feedparser.parse(podcast["rss"])

    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(f"RSS parse failed: {feed.bozo_exception}")

    history_mode = os.getenv("PODCAST_HISTORY_MODE", "false").lower() in {"1", "true", "yes", "on"}
    requested_count = int(os.getenv("PODCAST_COUNT", "0") or "0")

    if history_mode:
        entries = list(feed.entries)
        print(f"History mode: RSS exposes {len(entries)} episodes for this feed.")
    elif requested_count > 0:
        entries = list(feed.entries[:requested_count])
        print(f"Latest mode: checking the newest {len(entries)} episodes for this feed.")
    else:
        entries = list(feed.entries[: int(settings.get("max_episodes_per_feed", 10))])

    seen = state.setdefault("episodes", {})
    force_items = []
    try:
        force_items = json.loads(os.getenv("PODCAST_FORCE_EPISODES", "[]") or "[]")
    except json.JSONDecodeError:
        force_items = []
    force_targets = os.getenv("PODCAST_FORCE_TARGETS", "")
    force_count = int(os.getenv("PODCAST_FORCE_COUNT", "0") or "0")
    force_keys = {
        episode_key(entry)
        for entry in list(feed.entries)[:force_count]
    } if force_count > 0 else set()
    force_match = lambda entry, key: key in force_keys or any(
        item == key or item.casefold() == (entry.get("title", "") or "").strip().casefold()
        for item in force_items
    )
    feeds = state.setdefault("feeds", {})
    yemos_episodes = yemos_state.setdefault("episodes", {})
    first_run = podcast_id not in feeds

    if first_run and settings.get("bootstrap_existing_as_seen", True):
        for entry in entries:
            key = episode_key(entry)
            seen.setdefault(
                key,
                {
                    "podcast_id": podcast_id,
                    "title": entry.get("title", "Untitled"),
                    "status": "bootstrap",
                    "seen_at": utc_now(),
                },
            )
        feeds[podcast_id] = {
            "initialized": True,
            "last_checked": utc_now(),
            "last_error": None,
        }
        save_state(state)
        print(f"Initialized with {len(entries)} existing episodes.")
        return 0

    new_count = 0

    for entry in reversed(entries):
        key = episode_key(entry)
        current = seen.get(key)
        yemos_record = yemos_episodes.get(key, {})
        forced = force_match(entry, key)
        if forced:
            if "Drive" in force_targets:
                current = None
                seen.pop(key, None)
            if "Yemos" in force_targets:
                yemos_episodes.pop(key, None)
                if current:
                    current["yemos_status"] = "pending"
                    current.pop("yemos_path", None)
                    current.pop("yemos_error", None)
        title = entry.get("title", "Untitled")

        # Migrate the Yemos status already stored in the main state file.
        # This prevents re-uploading episodes that succeeded before the
        # separate Yemos state file was introduced.
        if (
            current
            and current.get("yemos_status") == "uploaded"
            and yemos_record.get("status") != "uploaded"
        ):
            yemos_record = {
                "podcast_id": podcast_id,
                "title": title,
                "status": "uploaded",
                "path": current.get("yemos_path"),
                "migrated_at": utc_now(),
            }
            yemos_episodes[key] = yemos_record
            save_yemos_state(yemos_state)
        audio_url = enclosure_url(entry)

        # A Drive upload is independent from Yemos. If Drive already has the
        # episode but Yemos does not, retry only Yemos instead of uploading
        # the episode to Drive again.
        if (
            current
            and current.get("drive_file_id")
            and settings.get("yemos_enabled", True)
            and yemos_record.get("status") != "uploaded"
            and audio_url
        ):
            filename = safe_filename(title, audio_url)
            branch = podcast.get("yemos_branch", "1")
            yemos_number = yemos_record.get("filename_stem")
            if not yemos_number:
                yemos_number = str(next_yemos_number(yemos_state, branch))
                yemos_record["filename_stem"] = yemos_number
                save_yemos_state(yemos_state)
            yemos_filename = f"{yemos_number}.wav"

            try:
                with tempfile.TemporaryDirectory(prefix="yemos_retry_") as temp_dir:
                    local_path = os.path.join(temp_dir, filename)

                    print(f"Retrying Yemos only: {title}")
                    download(
                        audio_url,
                        local_path,
                        int(settings.get("download_timeout_seconds", 1800)),
                    )

                    yemos_file = upload_yemos_audio(
                        local_path,
                        podcast["name"],
                        yemos_filename,
                        branch=branch,
                    )

                yemos_episodes[key] = {
                    "podcast_id": podcast_id,
                    "title": title,
                    "status": "uploaded",
                    "path": yemos_file.get("path"),
                    "filename_stem": yemos_number,
                    "uploaded_at": utc_now(),
                }
                save_yemos_state(yemos_state)

                current["yemos_status"] = "uploaded"
                current["yemos_path"] = yemos_file.get("path")
                current.pop("yemos_error", None)
                save_state(state)

                print(f"Yemos retry complete: {title}")
            except Exception as exc:
                yemos_episodes[key] = {
                    "podcast_id": podcast_id,
                    "title": title,
                    "status": "error",
                    "error": str(exc),
                    "updated_at": utc_now(),
                }
                save_yemos_state(yemos_state)
                print(f"WARNING: Yemos retry failed for {title}: {exc}")

            # Do not redownload/reupload to Drive in this pass.
            if current.get("status") in {"notified", "uploaded", "bootstrap"}:
                continue

        if current:
            status = current.get("status")
            notification_status = current.get("notification_status")

            if status in {"notified", "bootstrap"}:
                continue

            if status == "uploaded" and notification_status == "sent":
                continue

            if status == "uploaded" and current.get("drive_file_id"):
                if notify_existing_uploaded(podcast, current, notifications):
                    save_state(state)
                    new_count += 1
                continue

        if not audio_url:
            seen[key] = {
                "podcast_id": podcast_id,
                "title": title,
                "published": entry.get("published", ""),
                "status": "skipped_no_audio",
                "updated_at": utc_now(),
            }
            save_state(state)
            print(f"Skipping without audio enclosure: {title}")
            continue

        filename = safe_filename(title, audio_url)
        branch = podcast.get("yemos_branch", "1")
        yemos_number = str(next_yemos_number(yemos_state, branch))
        yemos_filename = f"{yemos_number}.wav"

        try:
            with tempfile.TemporaryDirectory(prefix="podcast_") as temp_dir:
                local_path = os.path.join(temp_dir, filename)

                print(f"Downloading: {title}")
                download(
                    audio_url,
                    local_path,
                    int(settings.get("download_timeout_seconds", 1800)),
                )

                print("Uploading to Google Drive...")
                drive_file = upload_audio(
                    local_path,
                    podcast.get("drive_folder") or podcast["name"],
                    filename,
                    settings.get("drive_root_folder", "Podcasts"),
                    episode_key=key,
                    podcast_id=podcast_id,
                )

                record = {
                    "podcast_id": podcast_id,
                    "title": title,
                    "published": entry.get("published", ""),
                    "audio_url": audio_url,
                    "drive_file_id": drive_file.get("id"),
                    "drive_url": drive_file.get("webViewLink"),
                    "status": "uploaded",
                    "notification_status": "pending",
                    "yemos_status": "pending",
                    "processed_at": utc_now(),
                }
                seen[key] = record
                feeds.setdefault(podcast_id, {})["last_checked"] = utc_now()
                feeds[podcast_id]["last_error"] = None
                save_state(state)

                if settings.get("yemos_enabled", True):
                    try:
                        print(f"Uploading to Yemos: {title} as {yemos_filename}")
                        yemos_file = upload_yemos_audio(
                            local_path,
                            podcast["name"],
                            yemos_filename,
                            branch=branch,
                        )
                        yemos_episodes[key] = {
                            "podcast_id": podcast_id,
                            "title": title,
                            "status": "uploaded",
                            "path": yemos_file.get("path"),
                            "filename_stem": yemos_number,
                            "uploaded_at": utc_now(),
                        }
                        save_yemos_state(yemos_state)

                        record["yemos_status"] = "uploaded"
                        record["yemos_path"] = yemos_file.get("path")
                        record.pop("yemos_error", None)
                        print(f"Yemos upload complete: {yemos_file.get('path')}")
                    except Exception as exc:
                        yemos_episodes[key] = {
                            "podcast_id": podcast_id,
                            "title": title,
                            "status": "error",
                            "error": str(exc),
                            "updated_at": utc_now(),
                        }
                        save_yemos_state(yemos_state)
                        record["yemos_status"] = "error"
                        record["yemos_error"] = str(exc)
                        print(f"WARNING: Yemos upload failed for {title}: {exc}")
                else:
                    record["yemos_status"] = "disabled"

                save_state(state)

            if notifications.get("enabled", True):
                queue_notification(podcast, record, drive_file)
                print(f"Notification queued: {title}")

            save_state(state)
            new_count += 1
            print(f"Done: {title}")

        except Exception as exc:
            seen[key] = {
                "podcast_id": podcast_id,
                "title": title,
                "published": entry.get("published", ""),
                "audio_url": audio_url,
                "status": "error",
                "error": str(exc),
                "updated_at": utc_now(),
            }
            feeds.setdefault(podcast_id, {})["last_error"] = str(exc)
            save_state(state)
            print(f"ERROR [{podcast['name']}] {title}: {exc}")

    feeds.setdefault(podcast_id, {})["last_checked"] = utc_now()
    save_state(state)
    save_yemos_state(yemos_state)
    return new_count



def main():
    config = load_config()
    state = load_state()
    yemos_state = load_yemos_state()

    podcasts = [p for p in config.get("podcasts", []) if p.get("enabled", True)]
    requested_ids = {
        item.strip()
        for item in os.getenv("PODCAST_IDS", "").split(",")
        if item.strip()
    }

    if requested_ids:
        known_ids = {p.get("id") for p in podcasts}
        unknown_ids = sorted(requested_ids - known_ids)
        if unknown_ids:
            raise SystemExit("Unknown or disabled podcast IDs: " + ", ".join(unknown_ids))
        podcasts = [p for p in podcasts if p.get("id") in requested_ids]

    if not podcasts:
        raise SystemExit("No enabled podcasts selected.")

    print(f"Starting podcast monitor for {len(podcasts)} podcast(s).")

    total_processed = 0
    failed_feeds = []
    run_uploads = []
    manifest_path = Path("data/run_uploads.json")
    manifest_path.write_text("[]\\n", encoding="utf-8")

    for podcast in podcasts:
        try:
            before_keys = set(state.get("episodes", {}).keys())
            total_processed += process_feed(podcast, config, state, yemos_state)
            for key in set(state.get("episodes", {}).keys()) - before_keys:
                record = state["episodes"].get(key, {})
                if not record.get("drive_file_id"):
                    continue
                destinations = ["Google Drive"]
                if record.get("yemos_status") == "uploaded":
                    destinations.append("ימות המשיח " + str(record.get("yemos_path", "")))
                run_uploads.append({
                    "podcast": podcast.get("name", ""),
                    "title": record.get("title", ""),
                    "destinations": destinations,
                })
            manifest_path.write_text(
                json.dumps(run_uploads, ensure_ascii=False, indent=2) + "\\n",
                encoding="utf-8",
            )
        except Exception as exc:
            failed_feeds.append((podcast.get("id", "unknown"), str(exc)))
            state.setdefault("feeds", {}).setdefault(podcast.get("id", "unknown"), {})["last_error"] = str(exc)
            state["feeds"][podcast.get("id", "unknown")]["last_checked"] = utc_now()
            save_state(state)
            print(f"ERROR feed [{podcast.get('name', podcast.get('id', 'unknown'))}]: {exc}")

    sent_records = []
    try:
        sent_records = flush_notifications()
        for record in sent_records:
            record["notification_status"] = "sent"
            record["status"] = "notified"
            record["notification_sent_at"] = utc_now()
        if sent_records:
            save_state(state)
            print(f"Sent notifications for {len(sent_records)} episode(s).")
    except Exception as exc:
        save_state(state)
        print(f"WARNING: failed to flush notifications: {exc}")

    save_state(state)
    save_yemos_state(yemos_state)

    print(
        f"Podcast monitor finished: {total_processed} episode(s) processed, "
        f"{len(failed_feeds)} feed(s) failed."
    )

    if failed_feeds and len(failed_feeds) == len(podcasts):
        details = "; ".join(f"{podcast_id}: {error}" for podcast_id, error in failed_feeds)
        raise SystemExit("All selected podcast feeds failed: " + details)


if __name__ == "__main__":
    main()
