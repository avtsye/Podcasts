import json
import os
from functools import wraps

import requests
from flask import Flask, jsonify, request, make_response, send_from_directory

app = Flask(__name__)
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard"))

REPO = os.getenv("GITHUB_REPOSITORY", "avtsye/Podcasts")
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.getenv("DASHBOARD_ORIGINS", os.getenv("DASHBOARD_ORIGIN", "*")).split(",")
    if origin.strip()
}
# RawGitHack is an approved dashboard host. Keep it explicitly allowed even
# if a Render environment variable is accidentally changed later.
ALLOWED_ORIGINS.update({"https://raw.githack.com", "https://avtsye.github.io"})
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


def headers():
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def apply_cors(response):
    origin = request.headers.get("Origin", "").rstrip("/")
    allowed = "*" in ALLOWED_ORIGINS or origin in ALLOWED_ORIGINS
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Dashboard-Password, Accept"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "86400"
        response.headers["Access-Control-Expose-Headers"] = "Content-Type"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["Vary"] = "Origin"
    return response


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS" and request.path.startswith("/api/"):
        return apply_cors(make_response("", 204))


@app.after_request
def cors(response):
    return apply_cors(response)


def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not PASSWORD:
            return jsonify(error="Dashboard password is not configured on the server."), 503
        if request.headers.get("X-Dashboard-Password", "") != PASSWORD:
            return jsonify(error="Unauthorized"), 401
        return fn(*args, **kwargs)
    return wrapper


def gh(method, path, **kwargs):
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not configured on the dashboard API.")
    response = requests.request(method, f"{API}/repos/{REPO}{path}", headers=headers(), timeout=45, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub API {response.status_code}: {response.text[:500]}")
    return response.json() if response.content else {}


def raw_json(path):
    response = requests.get(f"{RAW}/{REPO}/main/{path}", timeout=30, headers={"Cache-Control": "no-cache"})
    response.raise_for_status()
    return response.json()


@app.get("/")
def dashboard_index():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.get("/styles.css")
def dashboard_styles():
    return send_from_directory(DASHBOARD_DIR, "styles.css")


@app.get("/app.js")
def dashboard_script():
    response = send_from_directory(DASHBOARD_DIR, "app.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/health")
def health():
    return jsonify(ok=True, repo=REPO, github_token_configured=bool(TOKEN), password_configured=bool(PASSWORD))


@app.get("/api/overview")
@protected
def overview():
    config = raw_json("config/podcasts.json")
    state = raw_json("data/state.json")
    yemos = raw_json("data/yemos_state.json")
    runs = gh("GET", "/actions/workflows/podcast-monitor.yml/runs?per_page=10").get("workflow_runs", [])
    episodes = state.get("episodes", {})
    return jsonify(
        podcasts=config.get("podcasts", []),
        settings=config.get("settings", {}),
        feeds=state.get("feeds", {}),
        episodes=episodes,
        yemos=yemos.get("episodes", {}),
        runs=[{
            "id": r["id"], "number": r["run_number"], "status": r["status"],
            "conclusion": r.get("conclusion"), "event": r["event"],
            "created_at": r["created_at"], "updated_at": r["updated_at"],
            "html_url": r["html_url"]
        } for r in runs],
        totals={
            "podcasts": len(config.get("podcasts", [])),
            "enabled": sum(1 for p in config.get("podcasts", []) if p.get("enabled", True)),
            "episodes": len(episodes),
            "drive_uploaded": sum(1 for e in episodes.values() if e.get("drive_file_id")),
            "yemos_uploaded": sum(1 for e in episodes.values() if e.get("yemos_status") == "uploaded"),
            "errors": sum(1 for e in episodes.values() if e.get("status") == "error" or e.get("yemos_status") == "error"),
        },
    )


@app.post("/form/run")
def form_run():
    supplied = request.form.get("password", "")
    if not PASSWORD or supplied != PASSWORD:
        return ("Unauthorized", 401)
    mode = request.form.get("mode", "latest")
    try:
        count = str(max(1, min(1000, int(request.form.get("count", "1")))))
    except ValueError:
        count = "1"
    podcasts = request.form.get("podcasts", "")
    if mode not in {"latest", "all"}:
        return ("Invalid mode", 400)
    inputs = {"mode": mode, "count": count, "podcasts": podcasts}
    gh("POST", "/actions/workflows/podcast-monitor.yml/dispatches", json={"ref": "main", "inputs": inputs})
    return ("OK", 200)


@app.post("/api/run")
@protected
def run_monitor():
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "latest")
    count = str(max(1, min(1000, int(body.get("count", 1)))))
    podcasts = body.get("podcasts") or []
    if mode not in {"latest", "all"}:
        return jsonify(error="Invalid mode"), 400
    inputs = {"mode": mode, "count": count, "podcasts": ",".join(podcasts)}
    gh("POST", "/actions/workflows/podcast-monitor.yml/dispatches", json={"ref": "main", "inputs": inputs})
    return jsonify(ok=True, message="Workflow dispatched", inputs=inputs)


@app.get("/api/runs")
@protected
def runs():
    data = gh("GET", "/actions/workflows/podcast-monitor.yml/runs?per_page=30")
    return jsonify(data.get("workflow_runs", []))


@app.get("/api/runs/<int:run_id>/jobs")
@protected
def jobs(run_id):
    return jsonify(gh("GET", f"/actions/runs/{run_id}/jobs").get("jobs", []))


@app.put("/api/podcasts/<podcast_id>")
@protected
def update_podcast(podcast_id):
    body = request.get_json(silent=True) or {}
    file_data = gh("GET", "/contents/config/podcasts.json")
    import base64
    config = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
    podcast = next((p for p in config.get("podcasts", []) if p.get("id") == podcast_id), None)
    if not podcast:
        return jsonify(error="Podcast not found"), 404
    for key in ("name", "rss", "drive_folder", "yemos_branch", "enabled"):
        if key in body:
            podcast[key] = body[key]
    if not str(podcast.get("yemos_branch", "")).isdigit():
        return jsonify(error="Yemos branch must be numeric"), 400
    content = base64.b64encode((json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()).decode()
    result = gh("PUT", "/contents/config/podcasts.json", json={
        "message": f"dashboard: update {podcast_id}",
        "content": content,
        "sha": file_data["sha"],
        "branch": "main",
    })
    return jsonify(ok=True, commit=result.get("commit", {}).get("sha"))


@app.errorhandler(Exception)
def handle_error(exc):
    return jsonify(error=str(exc)), 500
