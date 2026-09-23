import io
import json
import mimetypes
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _service():
    raw = os.environ.get("GOOGLE_TOKEN_JSON")
    if not raw:
        raise RuntimeError("GOOGLE_TOKEN_JSON is not configured.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_TOKEN_JSON is not valid JSON.") from exc
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _escape_query(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_folder(service, name, parent_id=None):
    query = "mimeType='application/vnd.google-apps.folder' and trashed=false and name='" + _escape_query(name) + "'"
    if parent_id:
        query += " and '" + _escape_query(parent_id) + "' in parents"
    result = service.files().list(
        q=query, spaces="drive", fields="files(id,name)", pageSize=10
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _ensure_folder(service, name, parent_id=None):
    existing = _find_folder(service, name, parent_id)
    if existing:
        return existing
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    return service.files().create(body=body, fields="id").execute()["id"]


def _find_existing_episode(service, folder_id, episode_key):
    query = (
        "trashed=false and '" + _escape_query(folder_id) + "' in parents "
        "and appProperties has { key='episode_key' and value='" + _escape_query(episode_key) + "' }"
    )
    result = service.files().list(
        q=query, spaces="drive",
        fields="files(id,name,webViewLink,size)", pageSize=1
    ).execute()
    files = result.get("files", [])
    return files[0] if files else None


def upload_audio(file_path, podcast_name, filename, root_name="Podcasts", episode_key=None, podcast_id=None):
    service = _service()
    root_id = _ensure_folder(service, root_name)
    folder_id = _ensure_folder(service, podcast_name, root_id)

    if episode_key:
        existing = _find_existing_episode(service, folder_id, episode_key)
        if existing:
            print(f"Drive already contains this episode: {existing['name']}")
            return existing

    media = MediaIoBaseUpload(
        io.FileIO(file_path, "rb"),
        mimetype=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        resumable=True,
        chunksize=8 * 1024 * 1024,
    )

    body = {"name": filename, "parents": [folder_id]}
    properties = {}
    if episode_key:
        properties["episode_key"] = episode_key
    if podcast_id:
        properties["podcast_id"] = podcast_id
    if properties:
        body["appProperties"] = properties

    return service.files().create(
        body=body,
        media_body=media,
        fields="id,name,webViewLink,size",
    ).execute()
