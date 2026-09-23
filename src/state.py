import json
from pathlib import Path

STATE_PATH = Path("data/state.json")

def load_state():
    if not STATE_PATH.exists():
        return {"feeds": {}, "episodes": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"feeds": {}, "episodes": {}}

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)
