# app/entity/entity.py
#
# Entity module — read and write the single entity record.
#
# The entity table has exactly one row (id = 1, enforced by CHECK constraint).
# It is the "file header" for the user's set of books: their name for this
# set of books, base currency, fiscal year start, and timezone.
#
# During first-run setup (Phase 4), the database is created and seeded with
# USD, root accounts, and placeholder financial-layer records — but the entity
# row is intentionally left empty. The user must name their entity before they
# can do anything else. That first-write is handled here.
#
# Phase 5 scope:
#   POST /entity        — first-run only; creates the entity row
#   GET  /entity        — read the current entity record
#   PUT  /entity/name   — update the entity name (only user-editable field now)
#
# Fields not exposed for editing in Phase 5:
#   base_currency_id        — always USD; currency picker deferred to Phase 6
#   fiscal_year_start_month — always 1 (January); adequate for personal finance
#   timezone                — defaults to America/Chicago; deferred to settings
#   closing_frequency       — always 'annual'; adequate for personal finance
#   current_period_start    — computed at creation time (Jan 1 of current year)

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.database import open_database
from app.dependencies import get_current_token, get_db_file_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entity", tags=["entity"])


# =============================================================================
# Request / response models
# =============================================================================

class EntityCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description=(
        "Display name for this set of books. "
        "Examples: 'Stephen and Olga Nolan', 'Nolan Household Finances'."
    ))


class EntityUpdateNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class EntityResponse(BaseModel):
    id: int
    name: str
    base_currency_symbol: str
    fiscal_year_start_month: int
    timezone: str
    closing_frequency: str
    current_period_start: str
    schema_version: str
    created_at: str
    updated_at: str


# =============================================================================
# Helpers
# =============================================================================

def _row_to_response(row) -> EntityResponse:
    """Convert a sqlite3.Row from the entity query to an EntityResponse."""
    return EntityResponse(
        id=row["id"],
        name=row["name"],
        base_currency_symbol=row["symbol"],
        fiscal_year_start_month=row["fiscal_year_start_month"],
        timezone=row["timezone"],
        closing_frequency=row["closing_frequency"],
        current_period_start=row["current_period_start"],
        schema_version=row["schema_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _fetch_entity(conn):
    """
    Fetch the entity row joined with its base currency symbol.
    Returns a sqlite3.Row, or None if the entity has not been created yet.
    """
    return conn.execute("""
        SELECT
            e.id,
            e.name,
            c.symbol,
            e.fiscal_year_start_month,
            e.timezone,
            e.closing_frequency,
            e.current_period_start,
            e.schema_version,
            e.created_at,
            e.updated_at
        FROM entity e
        JOIN commodities c ON c.id = e.base_currency_id
        WHERE e.id = 1
    """).fetchone()


# =============================================================================
# Endpoints
# =============================================================================

@router.post("", response_model=EntityResponse, status_code=201)
async def create_entity(
    body: EntityCreateRequest,
    token: dict = Depends(get_current_token),
    file_id: str = Depends(get_db_file_id),
):
    """
    Create the entity record. First-run only.

    Returns 409 if the entity row already exists. The frontend should call
    GET /entity first and only call this endpoint if 404 is returned.

    The base currency is always USD for now. The current period starts on
    January 1 of the current calendar year. All other fields use the schema
    defaults defined in schema.sql.
    """
    current_period_start = date(date.today().year, 1, 1).isoformat()

    async with open_database(token, file_id) as conn:
        existing = conn.execute("SELECT id FROM entity WHERE id = 1").fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Entity already exists. Use PUT /entity/name to update.")

        usd_id = conn.execute(
            "SELECT id FROM commodities WHERE symbol = 'USD' AND commodity_type = 'currency'"
        ).fetchone()
        if not usd_id:
            raise HTTPException(status_code=500, detail="USD commodity not found. Database may be corrupted.")
        usd_id = usd_id[0]

        conn.execute("""
            INSERT INTO entity (id, name, base_currency_id, current_period_start)
            VALUES (1, ?, ?, ?)
        """, (body.name, usd_id, current_period_start))

        row = _fetch_entity(conn)

    logger.info("Entity created: '%s' (period start: %s)", body.name, current_period_start)
    return _row_to_response(row)


@router.get("", response_model=EntityResponse)
async def get_entity(
    token: dict = Depends(get_current_token),
    file_id: str = Depends(get_db_file_id),
):
    """
    Return the entity record.

    Returns 404 if the entity has not been created yet. The frontend uses
    this to detect first-run state and prompt the user to name their entity.
    """
    async with open_database(token, file_id) as conn:
        row = _fetch_entity(conn)

    if not row:
        raise HTTPException(status_code=404, detail="Entity not yet created. POST /entity to set up.")

    return _row_to_response(row)


@router.put("/name", response_model=EntityResponse)
async def update_entity_name(
    body: EntityUpdateNameRequest,
    token: dict = Depends(get_current_token),
    file_id: str = Depends(get_db_file_id),
):
    """
    Update the entity name. The entity row must already exist.
    """
    async with open_database(token, file_id) as conn:
        existing = conn.execute("SELECT id FROM entity WHERE id = 1").fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Entity not yet created. POST /entity to set up.")

        conn.execute("UPDATE entity SET name = ? WHERE id = 1", (body.name,))

        row = _fetch_entity(conn)

    logger.info("Entity name updated to: '%s'", body.name)
    return _row_to_response(row)
