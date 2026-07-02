# app/main.py
#
# Application entry point.
#
# Responsibilities:
#   - Load environment variables before anything else touches os.environ
#   - Initialize the OAuth client (must happen after env vars load)
#   - Configure middleware
#   - Register routers
#
# Routers registered here:
#   auth_router   — /auth/login, /auth/callback, /auth/me, /auth/logout
#   setup_router  — /setup/status, /setup/token, /setup/init, /setup/link
#   entity_router — /entity (GET, POST, PUT /entity/name)
#
# Future routers (Phases 6-8) will be added here as they are built:
#   commodities_router, accounts_router, transactions_router

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

# Environment variables must be loaded before any module that reads
# os.environ at import time. load_dotenv is a no-op if the .env file
# is absent (e.g. on Render, where env vars are set in the dashboard).
load_dotenv(Path(__file__).parent.parent / ".env")

from app.auth import init_oauth
from app.auth import router as auth_router
from app.db.setup import router as setup_router
from app.entity.entity import router as entity_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

init_oauth()

app = FastAPI(
    title="DollarCloud",
    description=(
        "Web-based double-entry accounting. "
        "User data lives on the user's own Google Drive."
    ),
    version="0.5.0",
)

# SameSite=none is required for the OAuth callback to work on Render.
# Google's redirect back to /auth/callback is a cross-site navigation.
# Browsers withhold SameSite=lax cookies on cross-site redirects, which
# drops the OAuth state and causes MismatchingStateError.
# SameSite=none requires the Secure flag, so https_only must also be True
# in production. Both are controlled by the HTTPS_ONLY env var: set to
# "true" on Render, leave unset for local dev.
_is_https = os.environ.get("HTTPS_ONLY", "false").lower() == "true"
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    https_only=_is_https,
    same_site="none" if _is_https else "lax",
)

app.include_router(auth_router)
app.include_router(setup_router)
app.include_router(entity_router)


@app.get("/")
async def root():
    return {"message": "Hello, World!"}
