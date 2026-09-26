import json
import os
from pathlib import Path

import requests

API_BASE = os.getenv("YEMOS_API_BASE", "https://www.call2all.co.il/ym/api").rstrip("/")


def api_call(name, data):
    response = requests.post(API_BASE + "/" + name, data=data, timeout=(20, 90))
    response.raise_for_status()
    payload = response.json()
    if payload.get("responseStatus") not in (None, "", "OK", "ok", True):
        raise RuntimeError(name + " failed: " + str(payload.get("message") or payload))
    return payload


def main():
    manifest_path = Path(os.getenv("YEMOS_RUN_MANIFEST", "data/run_uploads.json"))
    if not manifest_path.exists():
        print("No new podcast upload manifest; skipping Yemos run notification.")
        return

    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not items:
        print("No new podcast uploads; skipping Yemos run notification.")
        return

    token = os.environ["YEMOS_TOKEN"]
    branch = "1/99"
    list_id = "1"

    lines = ["דוח העלאת פודקאסטים חדשים."]
    for item in items:
        name = item.get("podcast", "")
        title = item.get("title", "")
        destinations = item.get("destinations", [])
        target_text = " וגם ".join(destinations) if destinations else "ללא יעד שהושלם"
        lines.append(f"{name}. {title}. עלה אל {target_text}.")
    lines.append(f"בסך הכל עלו {len(items)} פרקים חדשים. סוף הדוח.")
    report = " ".join(lines)

    # Send the tzintuk independently of the report branch. A missing report
    # extension must never prevent the phone notification itself.
    api_call("RunTzintuk", {
        "token": token,
        "phones": "tzl:" + list_id,
        "TzintukTimeOut": "15",
    })
    print(f"Sent tzintuk list {list_id}.")

    try:
        listing = api_call("GetIVR2Dir", {"token": token, "path": branch})
        numbers = []
        for item in listing.get("files", []):
            filename = str(item.get("name", ""))
            stem = filename.split(".", 1)[0]
            if stem.isdigit():
                numbers.append(int(stem))
        next_number = max(numbers) + 1 if numbers else 0
        filename = f"{next_number:03d}.tts"

        api_call("UploadTextFile", {
            "token": token,
            "what": f"ivr2:/{branch}/{filename}",
            "contents": report,
        })
        print(f"Uploaded run report {filename} to {branch}.")
    except Exception as exc:
        print(f"WARNING: tzintuk sent, but run report could not be written to {branch}: {exc}")


if __name__ == "__main__":
    main()
