import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HISTORY = Path("data/run_history.json")
PUBLIC_HISTORY = Path("docs/run-history.json")
TITLE = "📊 היסטוריית ריצות"
ISRAEL = ZoneInfo("Asia/Jerusalem")


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def api_headers():
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN", "")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def update_issue(entries):
    repo = os.getenv("GITHUB_REPOSITORY", "")
    headers = api_headers()
    if not repo or not headers:
        return

    api = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    response = requests.get(
        f"{api}/repos/{repo}/issues",
        headers=headers,
        params={"state": "open", "per_page": 100},
        timeout=60,
    )
    response.raise_for_status()
    issue = next(
        (x for x in response.json() if x.get("title") == TITLE and "pull_request" not in x),
        None,
    )

    lines = [
        "# 📊 היסטוריית ריצות",
        "",
        "העמוד מתעדכן אוטומטית ומציג את 20 הריצות האחרונות.",
        "",
        "| זמן בישראל | סוג | מצב | פרקים שהועלו | פודקאסטים עם שגיאה |",
        "|---|---|---|---:|---:|",
    ]
    for entry in entries[:20]:
        icon = "✅" if entry.get("status") == "success" else "❌"
        lines.append(
            f"| {entry.get('israel_time','')} | {entry.get('event','')} | "
            f"{icon} {entry.get('status','')} | {entry.get('uploads',0)} | "
            f"{entry.get('feed_errors',0)} |"
        )
    body = "\n".join(lines) + "\n"

    if issue is None:
        response = requests.post(
            f"{api}/repos/{repo}/issues",
            headers=headers,
            json={"title": TITLE, "body": body},
            timeout=60,
        )
    else:
        response = requests.patch(
            f"{api}/repos/{repo}/issues/{issue['number']}",
            headers=headers,
            json={"body": body},
            timeout=60,
        )
    response.raise_for_status()


def main():
    state = read_json(Path("data/state.json"), {"feeds": {}})
    manifest = read_json(Path("data/run_uploads.json"), [])
    feeds = state.get("feeds", {})
    errors = [key for key, value in feeds.items() if value.get("last_error")]

    now = datetime.now(timezone.utc)
    local = now.astimezone(ISRAEL)
    entry = {
        "run_id": os.getenv("RUN_ID", ""),
        "run_number": os.getenv("RUN_NUMBER", ""),
        "event": os.getenv("EVENT_NAME", ""),
        "status": os.getenv("RUN_STATUS", "unknown"),
        "utc_time": now.isoformat(),
        "israel_time": local.strftime("%d/%m/%Y %H:%M"),
        "uploads": len(manifest),
        "feed_errors": len(errors),
        "run_url": os.getenv("RUN_URL", ""),
        "items": manifest[:50],
    }

    history = read_json(HISTORY, {"runs": []})
    runs = [x for x in history.get("runs", []) if x.get("run_id") != entry["run_id"]]
    runs.insert(0, entry)
    history = {"updated_at": now.isoformat(), "runs": runs[:100]}

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(history, ensure_ascii=False, indent=2) + "\n"
    HISTORY.write_text(text, encoding="utf-8")
    PUBLIC_HISTORY.write_text(text, encoding="utf-8")
    update_issue(history["runs"])
    print(f"Recorded run {entry['run_id']} at {entry['israel_time']} Israel time.")


if __name__ == "__main__":
    main()
