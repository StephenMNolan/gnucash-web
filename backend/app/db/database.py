# app/db/database.py
#
# SQLite database lifecycle management.
#
# Responsibilities:
#   - Download the user's dollarcloud.db from Google Drive into a temp file
#   - Apply the schema to a brand-new database (first-run)
#   - Provide a context manager that opens a local SQLite connection,
#     yields it to the caller, then uploads the modified file back to Drive
#   - Validate that a downloaded file is a real DollarCloud database
#
# What this module does NOT do:
#   - OAuth or Drive authentication (see app/drive.py)
#   - First-run setup flow or folder picking (see app/db/setup.py)
#   - Any business logic (accounts, transactions, etc.)
#
# Usage pattern:
#   async with open_database(token, file_id) as conn:
#       conn.execute("SELECT * FROM entity")
#
# The context manager downloads the file on enter, yields a sqlite3.Connection,
# and uploads the (possibly modified) file on exit. If an exception is raised
# inside the block, the upload is skipped and the exception propagates.

import io
import logging
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from app import drive as drive_module

logger = logging.getLogger(__name__)

# Path to the schema file, relative to the backend root.
# Resolved at import time so we catch missing files early.
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Tables that must be present for a file to be considered a valid
# DollarCloud database. Used by validate_database().
_REQUIRED_TABLES = {
    "entity",
    "commodities",
    "institutions",
    "financial_accounts",
    "accounts",
    "payees",
    "transactions",
    "splits",
}


# =============================================================================
# Schema application
# =============================================================================

def _load_schema() -> str:
    """Read schema.sql from disk. Raises FileNotFoundError if missing."""
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Schema file not found at {_SCHEMA_PATH}. "
            "Ensure app/db/schema.sql is present in the repository."
        )
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def _apply_schema(conn: sqlite3.Connection) -> None:
    """
    Apply schema.sql to a new SQLite connection and seed required data.

    Seeding order matters due to foreign key dependencies:

      1. Schema DDL (tables, triggers, views, indexes)
      2. USD commodity          — no dependencies
      3. Root accounts          — depend on commodities (currency_id)
      4. Default institution    — no dependencies
      5. Default financial acct — depends on institutions and commodities

    Steps 4 and 5 seed the minimum financial-layer data required to satisfy
    the NOT NULL constraint on splits.financial_account_id during Track 1
    (accounting view) development, before real institutions and financial
    accounts are added in Track 2 (PFM view).

    The default institution and financial account are clearly labeled so they
    are recognizable as placeholders. They will be deactivated when the user
    sets up their real financial accounts in Track 2.

    executescript() is used for the DDL because the schema contains multiple
    statements including triggers and views. It implicitly commits any open
    transaction before running, which is correct for a fresh database.
    """
    schema_sql = _load_schema()
    conn.executescript(schema_sql)

    # ------------------------------------------------------------------
    # Step 2: Seed USD as the base currency.
    # The only commodity created automatically. All others are added by
    # the user via the Commodities module in a later phase.
    # ------------------------------------------------------------------
    conn.execute("""
        INSERT OR IGNORE INTO commodities (symbol, name, commodity_type)
        VALUES ('USD', 'US Dollar', 'currency')
    """)

    usd_id = conn.execute(
        "SELECT id FROM commodities WHERE symbol = 'USD' AND commodity_type = 'currency'"
    ).fetchone()[0]

    # ------------------------------------------------------------------
    # Step 3: Patch root accounts with currency_id.
    # The schema's INSERT OR IGNORE for root accounts intentionally omits
    # currency_id (it cannot be set until the commodity record exists).
    # ------------------------------------------------------------------
    conn.execute(
        "UPDATE accounts SET currency_id = ? WHERE currency_id IS NULL",
        (usd_id,),
    )

    # ------------------------------------------------------------------
    # Step 4: Seed the default institution.
    # A placeholder institution required by the financial_accounts FK.
    # Visible in the database but not surfaced in the Track 1 UI.
    # ------------------------------------------------------------------
    conn.execute(
        "INSERT OR IGNORE INTO institutions (name, notes) VALUES (?, ?)",
        (
            "Default Financial Institution",
            "Placeholder institution seeded during first-run setup. "
            "All Track 1 splits reference the default financial account "
            "under this institution. Replace with real institutions in Track 2.",
        ),
    )

    institution_id = conn.execute(
        "SELECT id FROM institutions WHERE name = 'Default Financial Institution'"
    ).fetchone()[0]

    # ------------------------------------------------------------------
    # Step 5: Seed the default financial account.
    # Referenced by splits.financial_account_id (NOT NULL) during Track 1.
    # All Track 1 transactions point here until real financial accounts
    # are set up in Track 2.
    # ------------------------------------------------------------------
    conn.execute(
        "INSERT OR IGNORE INTO financial_accounts "
        "(institution_id, name, account_type, currency_id, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            institution_id,
            "Default Financial Account",
            "other",
            usd_id,
            "Placeholder financial account seeded during first-run setup. "
            "All Track 1 splits reference this account. "
            "Replace with real financial accounts in Track 2.",
        ),
    )

    conn.commit()
    logger.info(
        "Schema applied. Seeded: USD (id=%s), default institution (id=%s), "
        "default financial account.",
        usd_id,
        institution_id,
    )


# =============================================================================
# Validation
# =============================================================================

def validate_database(conn: sqlite3.Connection) -> None:
    """
    Confirm that the connected SQLite file is a valid DollarCloud database.

    Checks that all required tables are present. Raises ValueError if any
    are missing. This catches the case where the user points the folder
    picker at a folder that already contains a non-DollarCloud SQLite file
    named dollarcloud.db.

    Does not verify data integrity; that is the job of the triggers and
    constraints in the schema itself.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    present = {row[0] for row in rows}
    missing = _REQUIRED_TABLES - present

    if missing:
        raise ValueError(
            f"Downloaded file is not a valid DollarCloud database. "
            f"Missing tables: {sorted(missing)}"
        )


# =============================================================================
# Low-level download / upload helpers
# =============================================================================

def _download_to_tempfile(token: dict, file_id: str) -> tempfile.NamedTemporaryFile:
    """
    Download a Drive file into a NamedTemporaryFile and return it (open).

    The caller is responsible for closing (and therefore deleting) the temp
    file when finished. The context manager open_database() handles this.

    Returns the temp file object positioned at byte 0.
    """
    content: bytes = drive_module.download_file(token, file_id)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=True)
    tmp.write(content)
    tmp.flush()
    tmp.seek(0)
    logger.debug("Downloaded Drive file %s to temp path %s.", file_id, tmp.name)
    return tmp


def _upload_from_tempfile(token: dict, file_id: str, tmp: tempfile.NamedTemporaryFile) -> None:
    """
    Upload the contents of a temp file back to an existing Drive file.

    Reads the temp file from the beginning so the full contents are sent
    regardless of where the file pointer currently sits.
    """
    tmp.seek(0)
    content: bytes = tmp.read()
    drive_module.update_file(token, file_id, content)
    logger.debug("Uploaded modified database back to Drive file %s.", file_id)


# =============================================================================
# Public API: context manager
# =============================================================================

@asynccontextmanager
async def open_database(token: dict, file_id: str):
    """
    Async context manager for read/write access to the user's database.

    On enter:
      - Downloads dollarcloud.db from Drive into a local temp file
      - Validates that the file is a real DollarCloud database
      - Opens a sqlite3.Connection with foreign keys enabled
      - Yields the connection

    On exit (no exception):
      - Commits any open transaction
      - Closes the connection
      - Uploads the modified file back to Drive
      - Deletes the temp file

    On exit (exception raised inside the block):
      - Rolls back any open transaction
      - Closes the connection
      - Skips the upload (Drive file is unchanged)
      - Deletes the temp file
      - Re-raises the exception

    Example:
        async with open_database(token, file_id) as conn:
            row = conn.execute("SELECT name FROM entity WHERE id = 1").fetchone()

    Note on async: the Drive download and upload are synchronous calls wrapped
    in this async context manager for consistent usage across the FastAPI
    codebase. Phase 4 does not require true async I/O for Drive operations.
    A future phase may move these to run_in_executor if performance demands it.
    """
    tmp = _download_to_tempfile(token, file_id)
    conn = sqlite3.connect(tmp.name)
    conn.row_factory = sqlite3.Row  # Rows accessible by column name
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        validate_database(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Upload happens here, outside the try/finally, so it only runs
    # if the block completed without raising.
    _upload_from_tempfile(token, file_id, tmp)
    tmp.close()


# =============================================================================
# Public API: create new database
# =============================================================================

def create_database(token: dict, folder_id: str) -> str:
    """
    Create a brand-new dollarcloud.db in the specified Drive folder.

    Steps:
      1. Create an empty SQLite file in a temp location
      2. Apply the full schema (tables, triggers, views, indexes)
      3. Seed required data: USD, root accounts, default institution,
         default financial account
      4. Upload the initialized file to Drive in the given folder
      5. Return the Drive file ID of the new file

    Called by the first-run setup flow in app/db/setup.py.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
        conn = sqlite3.connect(tmp.name)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            _apply_schema(conn)
        finally:
            conn.close()

        tmp.seek(0)
        content = tmp.read()

    file_id = drive_module.create_file(
        token=token,
        folder_id=folder_id,
        filename="dollarcloud.db",
        content=content,
        mimetype="application/x-sqlite3",
    )

    logger.info(
        "Created new dollarcloud.db in Drive folder %s (file_id=%s).",
        folder_id,
        file_id,
    )
    return file_id
