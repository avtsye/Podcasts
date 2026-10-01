import json
import os
from pathlib import Path

import requests

API = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN", "")
REPO = os.getenv("REPO") or os.getenv("GITHUB_REPOSITORY", "")
TITLE = "Podcast Temporary Runs"

if not TOKEN or not REPO:
    raise SystemExit("Missing GITHUB_TOKEN or GITHUB_REPOSITORY")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

r = requests.get(
    f"{API}/repos/{REPO}/issues",
    headers=headers,
    params={"state": "open", "per_page": 100},
    timeout=60,
)
r.raise_for_status()

issue = next(
    (
        item for item in r.json()
        if item.get("title") == TITLE
        and "pull_request" not in item
    ),
    None,
)

if issue is None:
    r = requests.post(
        f"{API}/repos/{REPO}/issues",
        headers=headers,
        json={
            "title": TITLE,
            "body": (
                "מרכז הריצות הידניות/הזמניות של מערכת הפודקאסטים.\n\n"
                "כל ריצה זמנית מתועדת כאן כתגובה נפרדת."
            ),
        },
        timeout=60,
    )
    r.raise_for_status()
    issue = r.json()

mode = os.getenv("MODE", "latest")
count = os.getenv("COUNT", "1")
podcasts = os.getenv("PODCASTS", "all enabled")
event = os.getenv("EVENT_NAME", "manual")
run_id = os.getenv("RUN_ID", "")
run_url = os.getenv("RUN_URL", "")

body = (
    "## ריצה זמנית\n\n"
    f"- **סוג הפעלה:** {event}\n"
    f"- **מצב:** {mode}\n"
    f"- **מספר פרקים:** {count}\n"
    f"- **פודקאסטים:** {podcasts}\n"
    f"- **Actions:** {run_url}\n"
    f"- **Run ID:** {run_id}\n"
)

r = requests.post(
    f"{API}/repos/{REPO}/issues/{issue['number']}/comments",
    headers=headers,
    json={"body": body},
    timeout=60,
)
r.raise_for_status()

manifest_path = Path("data/run_uploads.json")
try:
    uploads = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
except Exception:
    uploads = []

if uploads:
    lines = [
        f"## קבצים שהועלו בריצה {run_id}",
        "",
        f"**סה״כ:** {len(uploads)}",
        "",
    ]
    for item in uploads:
        podcast = item.get("podcast", "")
        title = item.get("title", "")
        drive_folder = item.get("drive_folder", "")
        drive_filename = item.get("drive_filename", "")
        drive_url = item.get("drive_url", "")
        yemos_path = item.get("yemos_path", "")
        lines.append(f"- **{podcast} — {title}**")
        if drive_folder or drive_filename:
            lines.append(
                f"  - Drive: `Podcasts/{drive_folder}/{drive_filename}`"
                + (f" — {drive_url}" if drive_url else "")
            )
        if yemos_path:
            lines.append(f"  - Yemos: `{yemos_path}`")

    chunks = []
    current = ""
    for line in lines:
        candidate = current + line + "\n"
        if len(candidate) > 55000 and current:
            chunks.append(current)
            current = "## קבצים שהועלו — המשך\n\n" + line + "\n"
        else:
            current = candidate
    if current:
        chunks.append(current)

    for chunk in chunks:
        rr = requests.post(
            f"{API}/repos/{REPO}/issues/{issue['number']}/comments",
            headers=headers,
            json={"body": chunk},
            timeout=60,
        )
        rr.raise_for_status()

print(f"Temporary run logged in issue #{issue['number']} with {len(uploads)} upload detail(s).")
