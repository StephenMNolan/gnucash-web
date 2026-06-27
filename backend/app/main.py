import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from pathlib import Path
from app.auth import router as auth_router, init_oauth
from fastapi import Depends
from app.dependencies import get_current_token
from app import drive

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

@app.get("/drive/test-write")
async def drive_test_write(token: dict = Depends(get_current_token)):
    file_id = drive.upload_test_file(token)
    return {"file_id": file_id}


@app.get("/drive/test-read/{file_id}")
async def drive_test_read(file_id: str, token: dict = Depends(get_current_token)):
    content = drive.read_file(token, file_id)
    return {"content": content}