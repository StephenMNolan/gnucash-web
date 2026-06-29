# app/drive.py
#
# Google Drive API wrapper.
#
# Responsibilities:
#   - Build an authenticated Drive service from a session token
#   - Create a new file in a specified folder
#   - Download the raw bytes of an existing file
#   - Update (overwrite) the contents of an existing file
#   - Fetch file metadata (name, parent folder, MIME type)
#
# What this module does NOT do:
#   - OAuth flow (see app/auth.py)
#   - SQLite operations (see app/db/database.py)
#   - First-run setup logic (see app/db/setup.py)
#
# All functions accept a token dict as returned by Authlib after the OAuth
# callback. The token must contain at minimum an 'access_token' key.
# A 'refresh_token' is included when present but Drive operations in this
# app do not attempt automatic token refresh; if a token has expired the
# caller will receive a 401 from the Drive API and should redirect the
# user to re-authenticate.

import io
import logging
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)


# =============================================================================
# Service construction
# =============================================================================

def get_drive_service(token: dict):
    """
    Build and return an authenticated Google Drive v3 service object.

    Credentials are constructed from the OAuth token stored in the session.
    The service object is not cached; a new one is built per request. This
    keeps the module stateless and avoids stale credential issues.
    """
    credentials = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    )
    return build("drive", "v3", credentials=credentials)


# =============================================================================
# File operations
# =============================================================================

def create_file(
    token: dict,
    folder_id: str,
    filename: str,
    content: bytes,
    mimetype: str = "application/octet-stream",
) -> str:
    """
    Create a new file in the specified Drive folder and return its file ID.

    The file is created with the given filename and MIME type. No duplicate
    checking is performed here; the caller (app/db/setup.py) is responsible
    for verifying that dollarcloud.db does not already exist in the folder
    before calling this function.

    Args:
        token:     Session OAuth token dict.
        folder_id: Drive folder ID where the file will be created.
        filename:  Name of the file as it will appear in Drive.
        content:   Raw bytes to write as the file body.
        mimetype:  MIME type of the file. Defaults to application/octet-stream.

    Returns:
        The Drive file ID of the newly created file.

    Raises:
        HttpError: If the Drive API returns an error (e.g. folder not found,
                   insufficient permissions).
    """
    service = get_drive_service(token)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mimetype)

    created = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, parents",
    ).execute()

    logger.info(
        "Created Drive file '%s' in folder %s (file_id=%s).",
        filename,
        folder_id,
        created["id"],
    )
    return created["id"]


def download_file(token: dict, file_id: str) -> bytes:
    """
    Download the full contents of a Drive file and return them as bytes.

    Uses MediaIoBaseDownload with chunked transfer to handle files of any
    size. For typical DollarCloud databases (well under 10 MB) this will
    complete in a single chunk.

    Args:
        token:   Session OAuth token dict.
        file_id: Drive file ID to download.

    Returns:
        Raw bytes of the file contents.

    Raises:
        HttpError: If the file does not exist or the token lacks access.
    """
    service = get_drive_service(token)
    request = service.files().get_media(fileId=file_id)

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = buffer.getvalue()
    logger.debug("Downloaded %d bytes from Drive file %s.", len(content), file_id)
    return content


def update_file(token: dict, file_id: str, content: bytes) -> None:
    """
    Overwrite the contents of an existing Drive file.

    This is a full replacement of the file body. Metadata (name, folder,
    MIME type) is left unchanged. This is the correct operation for saving
    a modified SQLite database back to Drive after a session.

    Args:
        token:   Session OAuth token dict.
        file_id: Drive file ID of the file to overwrite.
        content: New raw bytes to write as the file body.

    Raises:
        HttpError: If the file does not exist or the token lacks write access.
    """
    service = get_drive_service(token)

    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype="application/x-sqlite3",
    )

    service.files().update(
        fileId=file_id,
        media_body=media,
    ).execute()

    logger.debug("Updated Drive file %s (%d bytes).", file_id, len(content))


def get_file_metadata(token: dict, file_id: str) -> dict:
    """
    Fetch metadata for a Drive file without downloading its contents.

    Returns a dict with keys: id, name, mimeType, parents.
    The 'parents' value is a list of parent folder IDs (Drive files can
    in principle have multiple parents, though in practice DollarCloud
    always places files in a single folder).

    Used by the setup flow to verify that a stored file_id still resolves
    to a file the user can access, and to display the file's location.

    Args:
        token:   Session OAuth token dict.
        file_id: Drive file ID to look up.

    Returns:
        Dict with file metadata fields.

    Raises:
        HttpError: If the file does not exist or is not accessible.
                   A 404 means the user deleted or moved the file outside
                   the app; the setup flow should handle this by prompting
                   the user to re-run the folder picker.
    """
    service = get_drive_service(token)

    metadata = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, parents",
    ).execute()

    logger.debug("Fetched metadata for Drive file %s: %s.", file_id, metadata.get("name"))
    return metadata


def check_file_exists(token: dict, file_id: str) -> bool:
    """
    Return True if the Drive file exists and is accessible, False otherwise.

    A convenience wrapper around get_file_metadata that catches the 404
    HttpError and converts it to a boolean. Other errors (network failure,
    auth errors) are re-raised so the caller can handle them appropriately.

    Used by the setup flow to determine whether a session-stored file_id
    is still valid before attempting a download.
    """
    try:
        get_file_metadata(token, file_id)
        return True
    except HttpError as e:
        if e.resp.status == 404:
            return False
        raise
