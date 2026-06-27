import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from pathlib import Path
from app.auth import router as auth_router, init_oauth

load_dotenv(Path(__file__).parent.parent / ".env")

init_oauth()

app = FastAPI(title="DollarCloud")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
)

app.include_router(auth_router)


@app.get("/")
async def root():
    return {"message": "Hello, World!"}