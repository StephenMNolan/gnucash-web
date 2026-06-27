import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth

router = APIRouter()
oauth = OAuth()


def init_oauth():
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile https://www.googleapis.com/auth/drive.file",
        },
    )


@router.get("/auth/login")
async def login(request: Request):
    redirect_uri = os.environ["REDIRECT_URI"]
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    request.session["user"] = {
        "email": user["email"],
        "name": user["name"],
    }
    request.session["token"] = dict(token)
    return RedirectResponse(url="/auth/me")


@router.get("/auth/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/auth/login")
    return user


@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}