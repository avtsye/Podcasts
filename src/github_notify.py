import os
import requests

ISSUE_TITLE = "Podcast Notifications"
MAX_COMMENTS_PER_ISSUE = 2400

_PENDING = []


def _config():
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    api_url = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")

    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured.")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY is not configured.")

    return token, repo, api_url


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(method, url, token, **kwargs):
    response = requests.request(method, url, headers=_headers(token), timeout=60, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def _find_or_create_issue(token, repo, api_url):
    base = f"{api_url}/repos/{repo}/issues"
    response = _request("GET", base, token, params={"state": "open", "per_page": 100})

    candidates = [
        issue for issue in response
        if issue.get("title", "").startswith(ISSUE_TITLE)
        and "pull_request" not in issue
    ]
    candidates.sort(key=lambda item: item.get("number", 0), reverse=True)

    for issue in candidates:
        if int(issue.get("comments", 0) or 0) < MAX_COMMENTS_PER_ISSUE:
            return issue["number"]

    suffix = ""
    if candidates:
        suffix = f" #{len(candidates) + 1}"

    issue = _request(
        "POST",
        base,
        token,
        json={
            "title": ISSUE_TITLE + suffix,
            "body": (
                "This issue is used by Podcast Monitor for new-episode notifications.\n\n"
                "Each monitoring run adds one batched comment containing the new episodes.\n\n"
                f"A new issue is opened automatically before reaching {MAX_COMMENTS_PER_ISSUE} comments."
            ),
        },
    )
    return issue["number"]


def queue_notification(podcast, episode, drive_file):
    _PENDING.append(
        {
            "podcast": podcast["name"],
            "title": episode["title"],
            "published": episode.get("published", ""),
            "drive_url": drive_file.get("webViewLink") or episode.get("drive_url") or "",
            "drive_file_id": drive_file.get("id") or episode.get("drive_file_id") or "",
            "drive_filename": episode.get("drive_filename", ""),
            "drive_folder": episode.get("drive_folder", ""),
            "yemos_path": episode.get("yemos_path", ""),
            "record": episode,
        }
    )


def flush_notifications():
    if not _PENDING:
        return []

    token, repo, api_url = _config()
    issue_number = _find_or_create_issue(token, repo, api_url)

    header = ["## 🎙️ פרקי פודקאסט שהועלו", ""]
    blocks = []
    for item in _PENDING:
        drive_target = ""
        if item.get("drive_folder") or item.get("drive_filename"):
            drive_target = (
                f"Podcasts/{item.get('drive_folder','')}/"
                f"{item.get('drive_filename','')}"
            ).rstrip("/")
        drive_line = item.get("drive_url") or (f"https://drive.google.com/file/d/{item['drive_file_id']}/view" if item.get("drive_file_id") else "לא זמין")
        block = [
            f"### {item['podcast']} — {item['title']}",
            f"- **פורסם:** {item['published']}",
            f"- **קובץ Drive:** {drive_target or 'לא זמין'}",
            f"- **קישור Drive:** {drive_line}",
        ]
        if item.get("yemos_path"):
            block.append(f"- **Yemos:** {item['yemos_path']}")
        block.append("")
        blocks.append("\n".join(block))

    # GitHub comments are size-limited. Split large full-history reports
    # into multiple comments without dropping any uploaded item.
    comments = []
    current = "\n".join(header)
    for block in blocks:
        candidate = current + block + "\n"
        if len(candidate) > 55000 and current.strip():
            comments.append(current)
            current = "## 🎙️ פרקי פודקאסט שהועלו — המשך\n\n" + block + "\n"
        else:
            current = candidate
    if current.strip():
        comments.append(current)

    url = f"{api_url}/repos/{repo}/issues/{issue_number}/comments"
    for body in comments:
        _request("POST", url, token, json={"body": body})

    sent = [item["record"] for item in _PENDING]
    _PENDING.clear()
    return sent


def send_notification(podcast, episode, drive_file):
    queue_notification(podcast, episode, drive_file)
    sent = flush_notifications()
    return sent
