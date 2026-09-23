import io
import json
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

def _service():
    info = json.loads(os.environ["GOOGLE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _find_folder(service, name, parent_id=None):
    safe = name.replace("'", "\\'")
    q = "mimeType='application/vnd.google-apps.folder' and trashed=false and name='" + safe + "'"
    if parent_id:
        q += " and '" + parent_id + "' in parents"
    result = service.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=10).execute()
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

def upload_audio(file_path, podcast_name, filename, root_name="Podcasts"):
    service = _service()
    root_id = _ensure_folder(service, root_name)
    folder_id = _ensure_folder(service, podcast_name, root_id)
    media = MediaIoBaseUpload(
        io.FileIO(file_path, "rb"),
        mimetype="audio/mpeg",
        resumable=True,
        chunksize=8 * 1024 * 1024
    )
    return service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media,
        fields="id,name,webViewLink,size"
    ).execute()
