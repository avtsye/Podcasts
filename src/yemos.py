import os
from pathlib import Path

import requests

API_BASE = os.getenv(
    "YEMOS_API_BASE",
    "https://www.call2all.co.il/ym/api",
).rstrip("/")


class YemosError(RuntimeError):
    pass


def _token():
    token = os.getenv("YEMOS_TOKEN", "").strip()
    if not token:
        raise YemosError("Missing YEMOS_TOKEN secret.")
    return token


def _safe_path_part(value):
    value = str(value or "").strip()
    value = value.replace("\\", "_").replace("/", "_")
    value = value.replace("\x00", "")
    return value or "podcast"


def upload_audio(local_path, podcast_name, filename, branch="1"):
    """
    Upload an audio file to Yemos HaMashiach.

    Destination:
        <branch>/<podcast_name>/<episode>.wav

    The API document specifies UploadFile as multipart/form-data and supports
    convertAudio=1 for converting common audio formats to telephony WAV.
    """
    source = Path(local_path)
    if not source.is_file():
        raise YemosError(f"Audio file not found: {source}")

    podcast_folder = _safe_path_part(podcast_name)
    base_name = Path(filename).stem
    base_name = _safe_path_part(base_name)
    destination = f"{_safe_path_part(branch)}/{podcast_folder}/{base_name}.wav"

    url = f"{API_BASE}/UploadFile"
    token = _token()

    with source.open("rb") as audio:
        response = requests.post(
            url,
            data={
                "token": token,
                "path": destination,
                "convertAudio": "1",
            },
            files={
                "file": (
                    source.name,
                    audio,
                    "application/octet-stream",
                )
            },
            timeout=(30, 1800),
        )

    if response.status_code >= 400:
        raise YemosError(
            f"UploadFile HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise YemosError(
            f"UploadFile returned non-JSON response: {response.text[:500]}"
        ) from exc

    # The API draft documents a JSON response containing the uploaded path.
    # Some deployments may also return an explicit error field.
    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("message")
        if error:
            raise YemosError(f"UploadFile failed: {error}")

    return {
        "path": destination,
        "response": payload,
    }
