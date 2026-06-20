import os
import jwt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.models import TokenResponse

router = APIRouter()
MAGIC_LINK_SECRET = os.getenv("MAGIC_LINK_SECRET", "super-secret-token-123")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

security = HTTPBearer()

def get_current_coach(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "coach":
            raise HTTPException(status_code=403, detail="Not a coach")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=403, detail="Invalid token")

@router.get("/magic-link", response_model=TokenResponse)
def magic_link(token: str):
    if token != MAGIC_LINK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid magic token")
    payload = {
        "sub": "coach",
        "role": "coach",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    access_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer"}
