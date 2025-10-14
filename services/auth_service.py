import os, jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET = os.getenv("AUTH_SECRET", "***")

security = HTTPBearer()

def validate_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        request.app.state.erp_api_token = token 
        return payload
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Required token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")