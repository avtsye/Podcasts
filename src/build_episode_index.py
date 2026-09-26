import json
from datetime import datetime, timezone
from pathlib import Path

import feedparser

CONFIG = Path("config/podcasts.json")
STATE = Path("data/state.json")
YEMOS_STATE = Path("data/yemos_state.json")
OUTPUT = Path("docs/episode-index.json")
STATUS_OUTPUT = Path("docs/status.json")


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def episode_key(entry):
    value = (entry.get("id") or entry.get("guid") or "").strip()
    if value:
        return value
    return (entry.get("link") or entry.get("title") or "").strip()


def main():
    cfg = read_json(CONFIG, {"podcasts": []})
    state = read_json(STATE, {"feeds": {}, "episodes": {}})
    ystate = read_json(YEMOS_STATE, {"episodes": {}})
    seen = state.get("episodes", {})
    yepisodes = ystate.get("episodes", {})
    feeds = state.get("feeds", {})

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "podcasts": [],
    }
    status = {
        "updated_at": result["updated_at"],
        "podcasts": [],
        "totals": {"configured": 0, "active": 0, "episodes": 0, "feed_errors": 0},
    }

    for podcast in cfg.get("podcasts", []):
        status["totals"]["configured"] += 1
        if podcast.get("enabled", True):
            status["totals"]["active"] += 1

        feed_error = feeds.get(podcast.get("id", ""), {}).get("last_error")
        if feed_error:
            status["totals"]["feed_errors"] += 1

        item_status = {
            "id": podcast.get("id"),
            "name": podcast.get("name"),
            "rss": podcast.get("rss"),
            "enabled": podcast.get("enabled", True),
            "yemos_branch": podcast.get("yemos_branch", ""),
            "feed_error": feed_error or "",
            "episode_count": 0,
        }

        if not podcast.get("enabled", True):
            status["podcasts"].append(item_status)
            continue

        feed = feedparser.parse(podcast["rss"])
        episodes = []
        for entry in feed.entries:
            key = episode_key(entry)
            if not key:
                continue
            srec = seen.get(key, {})
            yrec = yepisodes.get(key, {})
            drive_uploaded = bool(srec.get("drive_file_id"))
            yemos_uploaded = (
                yrec.get("status") == "uploaded"
                or srec.get("yemos_status") == "uploaded"
            )
            episodes.append({
                "key": key,
                "title": (entry.get("title") or "ללא כותרת").strip(),
                "published": (entry.get("published") or entry.get("updated") or "").strip(),
                "link": (entry.get("link") or "").strip(),
                "drive_uploaded": drive_uploaded,
                "drive_url": srec.get("drive_url", ""),
                "yemos_uploaded": yemos_uploaded,
                "yemos_path": yrec.get("path") or srec.get("yemos_path", ""),
            })

        item_status["episode_count"] = len(episodes)
        status["totals"]["episodes"] += len(episodes)
        result["podcasts"].append({
            "id": podcast["id"],
            "name": podcast["name"],
            "rss": podcast["rss"],
            "yemos_branch": podcast.get("yemos_branch", ""),
            "episodes": episodes,
            "error": str(getattr(feed, "bozo_exception", "")) if getattr(feed, "bozo", False) and not episodes else "",
        })
        status["podcasts"].append(item_status)
        print(f"{podcast['name']}: {len(episodes)} episode(s)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    STATUS_OUTPUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
