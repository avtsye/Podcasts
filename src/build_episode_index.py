import json
from datetime import datetime, timezone
from pathlib import Path

import feedparser

# Rebuilds docs/episode-index.json from the configured RSS feeds.
CONFIG = Path("config/podcasts.json")
OUTPUT = Path("docs/episode-index.json")


def episode_key(entry):
    value = (entry.get("id") or entry.get("guid") or "").strip()
    if value:
        return value
    return (entry.get("link") or entry.get("title") or "").strip()


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "podcasts": [],
    }

    for podcast in cfg.get("podcasts", []):
        if not podcast.get("enabled", True):
            continue
        feed = feedparser.parse(podcast["rss"])
        episodes = []
        for entry in feed.entries:
            key = episode_key(entry)
            if not key:
                continue
            episodes.append({
                "key": key,
                "title": (entry.get("title") or "ללא כותרת").strip(),
                "published": (entry.get("published") or entry.get("updated") or "").strip(),
                "link": (entry.get("link") or "").strip(),
            })
        result["podcasts"].append({
            "id": podcast["id"],
            "name": podcast["name"],
            "rss": podcast["rss"],
            "episodes": episodes,
            "error": str(getattr(feed, "bozo_exception", "")) if getattr(feed, "bozo", False) and not episodes else "",
        })
        print(f"{podcast['name']}: {len(episodes)} episode(s)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
