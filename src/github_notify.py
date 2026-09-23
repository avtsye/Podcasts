import os
import requests

ISSUE_TITLE = "Podcast Notifications"


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
                "Each new episode is added as a comment below."
            ),
        },
    )
    return issue["number"]


def send_notification(podcast, episode, drive_file):
    token, repo, api_url = _config()
    issue_number = _find_or_create_issue(token, repo, api_url)

    drive_url = drive_file.get("webViewLink") or episode.get("drive_url") or ""
    body = (
        "## 🎙️ New podcast episode\n\n"
        f"**Podcast:** {podcast['name']}\n\n"
        f"**Episode:** {episode['title']}\n\n"
        f"**Published:** {episode.get('published', '')}\n\n"
        f"**Google Drive:** {drive_url}\n"
    )

    url = f"{api_url}/repos/{repo}/issues/{issue_number}/comments"
    _request("POST", url, token, json={"body": body})
    return issue_number
