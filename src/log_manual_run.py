import os
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

print(f"Temporary run logged in issue #{issue['number']}.")
