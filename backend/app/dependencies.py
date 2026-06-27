from fastapi import Request, HTTPException

def get_current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def get_current_token(request: Request) -> dict:
    token = request.session.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token
