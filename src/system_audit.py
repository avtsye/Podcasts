import compileall
import json
import os
from pathlib import Path

import feedparser
import requests

# Audit is intentionally read-only.\nROOT = Path(".")
CONFIG = ROOT / "config" / "podcasts.json"
STATE = ROOT / "data" / "state.json"
YEMOS_STATE = ROOT / "data" / "yemos_state.json"
INDEX = ROOT / "docs" / "episode-index.json"

errors = []
warnings = []


def fail(msg):
    errors.append(msg)
    print("ERROR:", msg)


def warn(msg):
    warnings.append(msg)
    print("WARNING:", msg)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"{path}: invalid JSON: {exc}")
        return {}


print("== Python syntax ==")
if not compileall.compile_dir("src", quiet=1):
    fail("One or more Python files failed to compile.")

print("== Configuration ==")
cfg = read_json(CONFIG)
podcasts = cfg.get("podcasts", [])
if not podcasts:
    fail("No podcasts configured.")

for field in ("id", "name", "rss", "yemos_branch"):
    vals = [str(p.get(field, "")).strip() for p in podcasts]
    missing = [p.get("name") or p.get("id") or "unknown" for p, v in zip(podcasts, vals) if not v]
    if missing:
        fail(f"Missing {field}: {missing}")
    dupes = sorted({v for v in vals if v and vals.count(v) > 1})
    if dupes:
        fail(f"Duplicate {field}: {dupes}")

for p in podcasts:
    branch = str(p.get("yemos_branch", ""))
    if branch and not branch.isdigit():
        fail(f"{p.get('name')}: Yemos branch is not numeric: {branch}")

print("== State files ==")
state = read_json(STATE)
ystate = read_json(YEMOS_STATE)
known_ids = {p.get("id") for p in podcasts}
for key, rec in state.get("episodes", {}).items():
    pid = rec.get("podcast_id")
    if pid and pid not in known_ids:
        warn(f"state episode {key!r} references unknown podcast_id {pid!r}")
for key, rec in ystate.get("episodes", {}).items():
    pid = rec.get("podcast_id")
    if pid and pid not in known_ids:
        warn(f"Yemos state episode {key!r} references unknown podcast_id {pid!r}")

print("== Issue forms and workflow integration ==")
required_markers = {
    ".github/ISSUE_TEMPLATE/manual-download.yml": ["בחירת פודקאסטים", "מצב הורדה", "מספר פרקים אחרונים"],
    ".github/ISSUE_TEMPLATE/redownload.yml": ["בחירת פודקאסטים", "פרקים מסוימים להורדה חוזרת", "יעד ההורדה החוזרת"],
    ".github/ISSUE_TEMPLATE/podcast-manage.yml": ["פעולה", "שם הפודקאסט הקיים", "RSS"],
    ".github/ISSUE_TEMPLATE/status.yml": ["היקף"],
    ".github/ISSUE_TEMPLATE/podcast-list.yml": ["מה להציג"],
    "src/issue_dashboard.py": ["[הורדה חוזרת]", "[הורדה]", "[ניהול פודקאסט]", "[מצב]", "[רשימת פודקאסטים]"],
    ".github/workflows/podcast-monitor.yml": ["python -m src.monitor", "python -m src.manage_podcast", "python -m src.run_history"],
}
for path, markers in required_markers.items():
    p = Path(path)
    if not p.exists():
        fail(f"Missing required file: {path}")
        continue
    text = p.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            fail(f"{path}: missing integration marker {marker!r}")

print("== RSS feeds ==")
rss_counts = {}
for p in podcasts:
    if not p.get("enabled", True):
        continue
    parsed = feedparser.parse(p["rss"])
    count = len(parsed.entries)
    rss_counts[p["id"]] = count
    if count == 0:
        fail(f"{p['name']}: active RSS returned 0 episodes")
    else:
        print(f"RSS OK: {p['name']}: {count}")

print("== Public episode index ==")
index = read_json(INDEX)
indexed = {p.get("id"): p for p in index.get("podcasts", [])}
for p in podcasts:
    if not p.get("enabled", True):
        continue
    if p["id"] not in indexed:
        fail(f"{p['name']}: missing from episode index")
        continue
    index_count = len(indexed[p["id"]].get("episodes", []))
    if rss_counts.get(p["id"], 0) and index_count == 0:
        fail(f"{p['name']}: RSS has episodes but public index is empty")

print("== Google Drive read-only connectivity ==")
try:
    from src.drive import _service
    service = _service()
    result = service.files().list(
        pageSize=1,
        fields="files(id,name)",
        spaces="drive",
    ).execute()
    print(f"Drive OK: read {len(result.get('files', []))} sample item(s)")
except Exception as exc:
    fail(f"Google Drive read-only check failed: {exc}")

print("== Yemos read-only connectivity ==")
try:
    token = os.environ.get("YEMOS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("YEMOS_TOKEN is missing")
    response = requests.get(
        "https://www.call2all.co.il/ym/api/GetIVR2Dir",
        params={"token": token, "path": "ivr2:/1"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("responseStatus") not in (None, "", "OK", "ok", True):
        raise RuntimeError(str(payload)[:500])
    print("Yemos OK: GetIVR2Dir responded successfully")
except Exception as exc:
    fail(f"Yemos read-only check failed: {exc}")

print("== Summary ==")
print(f"Podcasts: {len(podcasts)}")
print(f"Errors: {len(errors)}")
print(f"Warnings: {len(warnings)}")

if errors:
    print("\nFAILED CHECKS:")
    for item in errors:
        print("-", item)
    raise SystemExit(1)

print("SYSTEM AUDIT PASSED")
