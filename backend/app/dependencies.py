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

def get_db_file_id(request: Request) -> str:
    file_id = request.session.get("db_file_id")
    if not file_id:
        raise HTTPException(status_code=400, detail="No database file linked to this session. Complete setup first.")
    return file_id
