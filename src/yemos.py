import os
import re
from pathlib import Path
from uuid import uuid4

import requests


API_BASE = os.getenv(
    "YEMOS_API_BASE",
    "https://www.call2all.co.il/ym/api",
).rstrip("/")

# Yemos documents a 50MB limit for a single UploadFile request.
# Use a smaller chunk to leave room below that limit.
CHUNK_SIZE = 8 * 1024 * 1024


class YemosError(RuntimeError):
    """Raised when an upload to Yemos HaMashiach fails."""


def _token():
    token = os.getenv("YEMOS_TOKEN", "").strip()
    if not token:
        raise YemosError("Missing YEMOS_TOKEN secret.")
    return token


def _safe_path_part(value):
    value = str(value or "").strip()
    value = value.replace("\\", "_").replace("/", "_")
    value = value.replace("\x00", "")
    value = re.sub(r'[<>:"|?*]+', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "episode"


def _safe_branch(value):
    value = str(value or "").strip() or "1"
    if not re.fullmatch(r"\d+", value):
        raise YemosError(
            f"Invalid Yemos branch: {value!r}. "
            "The configured branch must contain digits only."
        )
    return value


def _build_destination(filename, branch):
    safe_branch = _safe_branch(branch)
    base_name = Path(filename).stem

    if not re.fullmatch(r"\\d+", base_name):
        raise YemosError(
            f"Yemos filename must be numeric, got {filename!r}."
        )

    # All podcasts live under IVR branch 1. Each podcast gets a numeric
    # sub-branch, and every audio file has a numeric filename.
    return f"ivr2:/1/{safe_branch}/{base_name}.wav"


def _parse_response(response, operation="UploadFile"):
    try:
        payload = response.json()
    except ValueError as exc:
        raise YemosError(
            f"{operation} returned a non-JSON response: "
            f"{response.text[:500]}"
        ) from exc

    if not isinstance(payload, dict):
        raise YemosError(
            f"{operation} returned an unexpected response: {payload!r}"
        )

    response_status = payload.get("responseStatus")
    message = payload.get("message")
    message_code = payload.get("messageCode")

    if response_status not in (None, "", "OK", "ok", True):
        detail = message or "Unknown Yemos API error"
        if message_code not in (None, "", 0, "0"):
            detail = f"{detail} (messageCode={message_code})"
        raise YemosError(f"{operation} failed: {detail}")

    error = payload.get("error")
    if error:
        raise YemosError(f"{operation} failed: {error}")

    if message_code not in (None, "", 0, "0"):
        detail = message or "Unknown Yemos API error"
        raise YemosError(
            f"{operation} failed: {detail} (messageCode={message_code})"
        )

    if payload.get("success") is False:
        raise YemosError(
            f"{operation} failed: {message or 'Unknown Yemos API error'}"
        )

    return payload


def _upload_small(source, destination, token):
    with source.open("rb") as audio:
        response = requests.post(
            f"{API_BASE}/UploadFile",
            data={
                "token": token,
                "path": destination,
                "convertAudio": "1",
                "autoNumbering": "false",
                "tts": "0",
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

    return _parse_response(response)


def _upload_large(source, destination, token):
    total_size = source.stat().st_size
    total_parts = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    upload_uuid = str(uuid4())

    offset = 0

    with source.open("rb") as audio:
        for part_index in range(total_parts):
            chunk = audio.read(CHUNK_SIZE)

            if not chunk:
                raise YemosError(
                    f"Unexpected end of file while uploading part "
                    f"{part_index + 1}/{total_parts}."
                )

            chunk_size = len(chunk)

            data = {
                "token": token,
                "path": destination,
                "convertAudio": "1",
                "autoNumbering": "false",
                "tts": "0",
                "uploader": "yemot-admin",
                "qquuid": upload_uuid,
                "qqpartindex": str(part_index),
                "qqpartbyteoffset": str(offset),
                "qqchunksize": str(chunk_size),
                "qqtotalparts": str(total_parts),
                "qqtotalfilesize": str(total_size),
                "qqfilename": source.name,
            }

            response = requests.post(
                f"{API_BASE}/UploadFile",
                data=data,
                files={
                    "qqfile": (
                        source.name,
                        chunk,
                        "application/octet-stream",
                    )
                },
                timeout=(30, 1800),
            )

            _parse_response(
                response,
                operation=f"UploadFile part {part_index + 1}/{total_parts}",
            )

            offset += chunk_size

            print(
                f"Yemos upload progress: "
                f"{part_index + 1}/{total_parts}"
            )

    response = requests.post(
        f"{API_BASE}/UploadFile?done",
        data={
            "token": token,
            "path": destination,
            "convertAudio": "1",
            "autoNumbering": "false",
            "tts": "0",
            "uploader": "yemot-admin",
            "qquuid": upload_uuid,
            "qqfilename": source.name,
            "qqtotalfilesize": str(total_size),
            "qqtotalparts": str(total_parts),
        },
        timeout=(30, 1800),
    )

    return _parse_response(response, operation="UploadFile finalization")


def upload_audio(local_path, podcast_name, filename, branch="1"):
    """
    Upload an audio file to Yemos HaMashiach.

    The podcast uses its configured numeric Yemos branch directly:

        ivr2:/1/<branch>/<number>.wav

    The existing monitor passes podcast_name for logging/compatibility.
    The podcast name is never inserted into the Yemos path.
    """

    source = Path(local_path)

    if not source.is_file():
        raise YemosError(f"Audio file not found: {source}")

    size = source.stat().st_size

    if size <= 0:
        raise YemosError(f"Audio file is empty: {source}")

    destination = _build_destination(filename, branch)
    token = _token()

    print(
        f"Yemos upload: podcast={podcast_name!r}, "
        f"branch={branch!r}, size={size} bytes, "
        f"destination={destination!r}"
    )

    try:
        if size <= 49 * 1024 * 1024:
            payload = _upload_small(
                source,
                destination,
                token,
            )
        else:
            print(
                f"Yemos upload: file is {size} bytes; "
                "using chunked UploadFile."
            )
            payload = _upload_large(
                source,
                destination,
                token,
            )
    except requests.RequestException as exc:
        raise YemosError(
            f"UploadFile request failed: {exc}"
        ) from exc

    return {
        "path": destination,
        "response": payload,
    }
