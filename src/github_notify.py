import os
import requests

ISSUE_TITLE = "Podcast Notifications"

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

    for issue in response:
        if issue.get("title") == ISSUE_TITLE and "pull_request" not in issue:
            return issue["number"]

    issue = _request(
        "POST",
        base,
        token,
        json={
            "title": ISSUE_TITLE,
            "body": (
                "This issue is used by Podcast Monitor for new-episode notifications.\n\n"
                "Each monitoring run adds one batched comment containing the new episodes."
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
            "record": episode,
        }
    )


def flush_notifications():
    if not _PENDING:
        return []

    token, repo, api_url = _config()
    issue_number = _find_or_create_issue(token, repo, api_url)

    lines = ["## 🎙️ New podcast episodes", ""]
    for item in _PENDING:
        lines.extend(
            [
                f"### {item['podcast']}",
                f"**Episode:** {item['title']}",
                f"**Published:** {item['published']}",
                f"**Google Drive:** {item['drive_url']}",
                "",
            ]
        )

    url = f"{api_url}/repos/{repo}/issues/{issue_number}/comments"
    _request("POST", url, token, json={"body": "\n".join(lines)})

    sent = [item["record"] for item in _PENDING]
    _PENDING.clear()
    return sent


def send_notification(podcast, episode, drive_file):
    queue_notification(podcast, episode, drive_file)
    sent = flush_notifications()
    return sent
