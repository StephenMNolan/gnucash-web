# app/db/setup.py
#
# First-run setup flow for DollarCloud.
#
# Responsibilities:
#   - Report whether the current session has a linked database file
#   - Provide the access token to the frontend for the Drive Picker widget
#   - Search a chosen folder for an existing dollarcloud.db
#   - Create a new database in the chosen folder (if none exists)
#   - Link an existing database found in the chosen folder
#   - Store the resulting Drive file ID in the session
#
# Endpoints:
#   GET  /setup/status        Is setup complete for this session?
#   GET  /setup/token         Return the access token for the Drive Picker
#   POST /setup/init          Create or link a database in the chosen folder
#   POST /setup/link          Explicitly link an existing file by file ID
#
# Flow (happy path, new user):
#   1. Frontend calls GET /setup/status -> { "ready": false }
#   2. Frontend launches Drive Picker using token from GET /setup/token
#   3. User picks a folder; frontend POSTs folder_id to /setup/init
#   4. Backend searches folder for dollarcloud.db
#      a. Not found: create new database, store file_id in session
#      b. Found: return candidate to frontend for user confirmation
#   5. If (b), frontend asks user to confirm; on confirm, POST to /setup/link
#   6. Session now contains db_file_id; app is ready
#
# The Drive Picker is a Google-provided JavaScript widget. It runs entirely
# in the browser and requires an access_token to initialize. The /setup/token
# endpoint provides this. The Picker returns a folder ID (not a file ID)
# when the user selects a destination folder.

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from googleapiclient.errors import HttpError
from pydantic import BaseModel

from app import drive as drive_module
from app.db.database import create_database, validate_database
from app.dependencies import get_current_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/setup", tags=["setup"])

# Filename used for the database on Drive. Defined once here so that
# the search query and the create call always use the same string.
DB_FILENAME = "dollarcloud.db"


# =============================================================================
# Request / response models
# =============================================================================

class InitRequest(BaseModel):
    folder_id: str
    # The Drive folder ID selected by the user via the Drive Picker.
    # Must be a real folder ID, not a file ID.


class LinkRequest(BaseModel):
    file_id: str
    # The Drive file ID of an existing dollarcloud.db that the user
    # has confirmed they want to link to this session.


class SetupStatusResponse(BaseModel):
    ready: bool
    # True if db_file_id is present in the session and the file is
    # accessible on Drive. False if setup is needed.


class InitResponse(BaseModel):
    status: str
    # One of: "created", "existing_found"
    file_id: str
    # The Drive file ID, whether newly created or already present.
    message: str
    # Human-readable description of what happened.


# =============================================================================
# Helpers
# =============================================================================

def _search_folder_for_db(token: dict, folder_id: str) -> str | None:
    """
    Search a Drive folder for a file named dollarcloud.db.

    Returns the file ID if found, None if not found.

    Uses the Drive Files.list API with a query that restricts results to
    the specified parent folder and the exact filename. The query is case-
    sensitive on most Drive backends.

    If multiple files with that name exist in the folder (which should not
    happen in normal use), the first result is returned. The Drive API
    returns results in an unspecified order in this case.
    """
    service = drive_module.get_drive_service(token)

    query = (
        f"name = '{DB_FILENAME}' "
        f"and '{folder_id}' in parents "
        f"and trashed = false"
    )

    response = service.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        pageSize=5,
    ).execute()

    files = response.get("files", [])

    if not files:
        logger.debug("No %s found in folder %s.", DB_FILENAME, folder_id)
        return None

    found_id = files[0]["id"]
    logger.info(
        "Found existing %s in folder %s (file_id=%s).",
        DB_FILENAME,
        folder_id,
        found_id,
    )
    return found_id


def _validate_existing_file(token: dict, file_id: str) -> None:
    """
    Download a candidate existing file and validate it is a real
    DollarCloud database.

    Raises ValueError if the file fails validation (e.g. it is a SQLite
    file from a different application, or not a SQLite file at all).
    Raises HttpError if the file cannot be downloaded.

    This protects against the case where the user has a file named
    dollarcloud.db in their chosen folder that belongs to something else.
    """
    import io
    import sqlite3
    import tempfile

    content = drive_module.download_file(token, file_id)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()

        conn = sqlite3.connect(tmp.name)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            validate_database(conn)
        finally:
            conn.close()


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    request: Request,
    token: dict = Depends(get_current_token),
):
    """
    Report whether this session has a linked, accessible database.

    The frontend calls this on every page load to decide whether to show
    the main application or redirect to the setup flow.

    Checks:
      1. Is db_file_id present in the session?
      2. Is that file still accessible on Drive?

    If the file has been deleted or moved outside the app, ready=False is
    returned and db_file_id is cleared from the session so the user is
    prompted to re-run the folder picker.
    """
    file_id = request.session.get("db_file_id")

    if not file_id:
        return SetupStatusResponse(ready=False)

    # Verify the stored file ID still resolves.
    accessible = drive_module.check_file_exists(token, file_id)

    if not accessible:
        logger.warning(
            "Stored db_file_id %s is no longer accessible. Clearing from session.",
            file_id,
        )
        del request.session["db_file_id"]
        return SetupStatusResponse(ready=False)

    return SetupStatusResponse(ready=True)


@router.get("/token")
async def setup_token(token: dict = Depends(get_current_token)):
    """
    Return the OAuth access token for use by the Drive Picker widget.

    The Drive Picker is a JavaScript widget that runs in the browser and
    requires an access_token to authenticate with Google. This endpoint
    exposes only the access_token, not the full session token (which also
    contains the refresh_token).

    The access_token is already visible to anyone who can read the session
    cookie, so exposing it here does not increase the attack surface.
    It expires after one hour, consistent with the overall session lifetime.
    """
    return {"access_token": token["access_token"]}


@router.post("/init", response_model=InitResponse)
async def setup_init(
    body: InitRequest,
    request: Request,
    token: dict = Depends(get_current_token),
):
    """
    Initialize the database in the folder the user selected via the Drive Picker.

    Two outcomes are possible:

    "created": No dollarcloud.db was found in the folder. A new database
    was created and its file ID stored in the session. The app is ready.

    "existing_found": A file named dollarcloud.db already exists in the
    folder and has passed validation as a real DollarCloud database. The
    file ID is returned but NOT yet stored in the session. The frontend
    must ask the user to confirm they want to link to this file, then call
    POST /setup/link to complete the process.

    If an existing dollarcloud.db is found but fails validation (it is not
    a real DollarCloud database), a 409 is returned with an explanation.
    The user should choose a different folder or rename the conflicting file.
    """
    folder_id = body.folder_id

    # Check for an existing file in the chosen folder.
    existing_file_id = _search_folder_for_db(token, folder_id)

    if existing_file_id is None:
        # Happy path: create a new database.
        try:
            file_id = create_database(token, folder_id)
        except HttpError as e:
            logger.error("Drive error creating database in folder %s: %s", folder_id, e)
            raise HTTPException(
                status_code=502,
                detail="Could not create the database file on Google Drive. "
                       "Check that the selected folder is accessible.",
            )

        request.session["db_file_id"] = file_id
        logger.info("New database created and session updated (file_id=%s).", file_id)

        return InitResponse(
            status="created",
            file_id=file_id,
            message=(
                f"{DB_FILENAME} has been created in the selected folder. "
                "Your DollarCloud books are ready."
            ),
        )

    # A file named dollarcloud.db exists. Validate it before offering to link.
    try:
        _validate_existing_file(token, existing_file_id)
    except ValueError as e:
        # File exists but is not a valid DollarCloud database.
        logger.warning(
            "Existing file %s in folder %s failed validation: %s",
            existing_file_id,
            folder_id,
            e,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"A file named {DB_FILENAME} already exists in the selected folder, "
                "but it does not appear to be a DollarCloud database. "
                "Please choose a different folder, or rename the existing file "
                "and try again."
            ),
        )
    except HttpError as e:
        logger.error("Drive error downloading existing file %s: %s", existing_file_id, e)
        raise HTTPException(
            status_code=502,
            detail="Found an existing database file but could not download it "
                   "for validation. Please try again.",
        )

    # Validation passed. Return the candidate to the frontend for confirmation.
    # Do NOT store in session yet; wait for the user to confirm via /setup/link.
    logger.info(
        "Existing valid database found in folder %s (file_id=%s). "
        "Awaiting user confirmation.",
        folder_id,
        existing_file_id,
    )

    return InitResponse(
        status="existing_found",
        file_id=existing_file_id,
        message=(
            f"An existing {DB_FILENAME} was found in the selected folder. "
            "Would you like to open it? Your existing data will be preserved."
        ),
    )


@router.post("/link")
async def setup_link(
    body: LinkRequest,
    request: Request,
    token: dict = Depends(get_current_token),
):
    """
    Link an existing Drive file to the current session.

    Called after the user confirms they want to open an existing database
    that was discovered by POST /setup/init. Validates the file one more
    time (in case something changed between the /init check and this call),
    then stores the file ID in the session.

    Also accepts a file ID that the user provides manually, for the recovery
    case where they know their file ID but their session has been cleared.
    In that case the frontend can provide a text field and call this endpoint
    directly, skipping the folder picker entirely.
    """
    file_id = body.file_id

    # Re-validate. The /init check may have been seconds ago or minutes ago.
    try:
        _validate_existing_file(token, file_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"The specified file is not a valid DollarCloud database: {e}",
        )
    except HttpError as e:
        if e.resp.status == 404:
            raise HTTPException(
                status_code=404,
                detail="The specified file could not be found on Google Drive. "
                       "It may have been moved or deleted.",
            )
        raise HTTPException(
            status_code=502,
            detail="Could not access the specified file on Google Drive.",
        )

    request.session["db_file_id"] = file_id
    logger.info("Session linked to existing database (file_id=%s).", file_id)

    return {
        "status": "linked",
        "file_id": file_id,
        "message": "Your existing DollarCloud database has been linked. Welcome back.",
    }
