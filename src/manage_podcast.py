import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path("config/podcasts.json")


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_id(name, existing):
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not base:
        base = "podcast_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    candidate = base
    n = 2
    while candidate in existing:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def valid_url(value):
    p = urlparse(value)
    return p.scheme in {"http", "https"} and bool(p.netloc)


def next_branch(items):
    used = {int(str(x.get("yemos_branch", ""))) for x in items if str(x.get("yemos_branch", "")).isdigit()}
    n = 1
    while n in used:
        n += 1
    return str(n)


def main():
    cfg = load()
    items = cfg.setdefault("podcasts", [])
    action = os.environ.get("ACTION", "").strip()
    current_name = os.environ.get("CURRENT_NAME", "").strip()
    name = os.environ.get("NAME", "").strip()
    rss = os.environ.get("RSS", "").strip()
    drive = os.environ.get("DRIVE_FOLDER", "").strip()
    branch = os.environ.get("YEMOS_BRANCH", "").strip()

    item = next((p for p in items if p.get("name") == current_name), None) if current_name else None

    if action == "הוספה":
        if not name or not rss:
            raise SystemExit("בהוספה חובה להזין שם ו-RSS")
        if not valid_url(rss):
            raise SystemExit("כתובת RSS אינה תקינה")
        if any(p.get("rss", "").strip() == rss for p in items):
            raise SystemExit("ה-RSS הזה כבר קיים במאגר")
        if any(p.get("name") == name for p in items):
            raise SystemExit("פודקאסט בשם הזה כבר קיים")
        pid = make_id(name, {p.get("id") for p in items})
        if branch:
            if not branch.isdigit():
                raise SystemExit("שלוחת Yemos חייבת להיות מספרית")
            if any(str(p.get("yemos_branch", "")) == branch for p in items):
                raise SystemExit("שלוחת Yemos כבר בשימוש")
        else:
            branch = next_branch(items)
        items.append({
            "id": pid,
            "name": name,
            "rss": rss,
            "enabled": True,
            "drive_folder": drive or name,
            "yemos_branch": branch,
        })
        print(f"Added {name} as {pid}, Yemos branch {branch}")
    else:
        if not item:
            raise SystemExit("יש לבחור פודקאסט קיים לפי השם המדויק")
        if action == "הפעלה":
            item["enabled"] = True
        elif action == "השבתה":
            item["enabled"] = False
        elif action == "עריכה":
            if rss:
                if not valid_url(rss):
                    raise SystemExit("כתובת RSS אינה תקינה")
                if any(p is not item and p.get("rss", "").strip() == rss for p in items):
                    raise SystemExit("ה-RSS הזה כבר משויך לפודקאסט אחר")
                item["rss"] = rss
            if name:
                if any(p is not item and p.get("name") == name for p in items):
                    raise SystemExit("כבר קיים פודקאסט בשם החדש")
                item["name"] = name
            if drive:
                item["drive_folder"] = drive
            if branch:
                if not branch.isdigit():
                    raise SystemExit("שלוחת Yemos חייבת להיות מספרית")
                if any(p is not item and str(p.get("yemos_branch", "")) == branch for p in items):
                    raise SystemExit("שלוחת Yemos כבר בשימוש")
                item["yemos_branch"] = branch
        else:
            raise SystemExit("פעולת ניהול לא מוכרת")
        print(f"Updated {item.get('name')}")

    save(cfg)


if __name__ == "__main__":
    main()
