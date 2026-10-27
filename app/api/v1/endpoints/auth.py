import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from app.core.config import get_settings
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse, VerifyTokenResponse

logger = logging.getLogger("translation-agent-backend.api.v1.endpoints.auth")
router = APIRouter()
security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate Demo User and Issue Session JWT",
)
async def login(payload: LoginRequest):
    settings = get_settings()

    is_user_valid = secrets.compare_digest(payload.username, settings.DEMO_AUTH_USERNAME)
    is_pass_valid = secrets.compare_digest(payload.password, settings.DEMO_AUTH_PASSWORD)

    if not (is_user_valid and is_pass_valid):
        logger.warning(f"Failed login attempt for username: {payload.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    expire_time = datetime.now(timezone.utc) + timedelta(hours=settings.DEMO_JWT_EXPIRE_HOURS)
    exp_timestamp = int(expire_time.timestamp())

    token_claims = {
        "sub": payload.username,
        "role": "admin",
        "exp": exp_timestamp,
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }

    token = jwt.encode(token_claims, settings.DEMO_JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(f"Demo user '{payload.username}' logged in successfully.")

    return LoginResponse(
        token=token,
        token_type="Bearer",
        expires_at=exp_timestamp,
        user=UserResponse(username=payload.username, role="admin"),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Verify Current Session Token and Return User Profile",
)
async def get_current_user_profile(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.DEMO_JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        return UserResponse(username=payload.get("sub", "admin"), role=payload.get("role", "admin"))
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
