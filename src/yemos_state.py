import json
from pathlib import Path

YEMOS_STATE_PATH = Path("data/yemos_state.json")


def load_yemos_state():
    if not YEMOS_STATE_PATH.exists():
        return {"episodes": {}}

    try:
        data = json.loads(
            YEMOS_STATE_PATH.read_text(encoding="utf-8")
        )
        if not isinstance(data, dict):
            return {"episodes": {}}

        data.setdefault("episodes", {})
        return data
    except Exception:
        return {"episodes": {}}


def next_yemos_number(state, branch):
    """Reserve the next numeric filename for a Yemos sub-branch."""
    branch = str(branch or "1")
    counters = state.setdefault("next_numbers", {})
    number = int(counters.get(branch, 1))
    counters[branch] = number + 1
    return number


def save_yemos_state(state):
    YEMOS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    tmp = YEMOS_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(YEMOS_STATE_PATH)
