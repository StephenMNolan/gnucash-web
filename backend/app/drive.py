import io
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload


def get_drive_service(token: dict):
    credentials = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    )
    return build("drive", "v3", credentials=credentials)


def upload_test_file(token: dict) -> str:
    service = get_drive_service(token)
    content = b"Hello from DollarCloud!"
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
    file_metadata = {"name": "dollarcloud-test.txt"}
    created = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name"
    ).execute()
    return created["id"]


def read_file(token: dict, file_id: str) -> str:
    service = get_drive_service(token)
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8")