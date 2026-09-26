import json
from pathlib import Path

import feedparser

CONFIG = Path("config/podcasts.json")


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    podcasts = cfg.get("podcasts", [])

    print("## 📋 פודקאסטים, RSS ושלוחות Yemos\n")
    print("| פודקאסט | RSS | מצב RSS | שלוחת Yemos | מצב |")
    print("|---|---|---|---:|---|")

    for p in podcasts:
        feed_state = "לא נבדק"
        try:
            parsed = feedparser.parse(p.get("rss", ""))
            if parsed.entries:
                feed_state = f"✅ תקין ({len(parsed.entries)} פרקים)"
            else:
                feed_state = "❌ שגיאה/ריק"
        except Exception:
            feed_state = "❌ שגיאה"

        status = "✅ פעיל" if p.get("enabled", True) else "⏸️ מושבת"
        rss = p.get("rss", "").replace("|", "%7C")
        print(
            f"| {p.get('name','')} | {rss} | {feed_state} | "
            f"{p.get('yemos_branch','—')} | {status} |"
        )

    print(f"\nסה״כ: **{len(podcasts)}** פודקאסטים.")


if __name__ == "__main__":
    main()
