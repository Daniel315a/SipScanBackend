import os
from datetime import datetime, timezone

import jwt
from jwt import InvalidTokenError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET = os.getenv("AUTH_SECRET", "***")

security = HTTPBearer()


def _decode_and_check_expiry(token: str) -> dict:
    """Decode the JWT and validate the custom 'fin' expiration field."""
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    fin_raw = payload.get("fin")
    if fin_raw is None:
        raise HTTPException(status_code=401, detail="Token missing expiration field")

    fin = datetime.fromisoformat(fin_raw.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > fin:
        raise HTTPException(status_code=401, detail="Required token has expired")

    return payload


def validate_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = _decode_and_check_expiry(credentials.credentials)
    request.app.state.erp_api_token = credentials.credentials
    return payload