import base64
import datetime
from typing import Optional
import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyCookie
from app.config import settings

# Initialize Fernet cipher for token encryption at rest
def _get_fernet() -> Fernet:
    raw_key = settings.TOKEN_ENCRYPTION_KEY
    if not raw_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is missing or empty in configuration")
    key = raw_key.encode("utf-8")
    try:
        return Fernet(key)
    except Exception as e:
        raise ValueError(f"Invalid TOKEN_ENCRYPTION_KEY provided: {e}. Key must be 32 url-safe base64-encoded bytes.")

def encrypt_token(plain_token: str) -> str:
    """Encrypt OAuth access/refresh token for database storage."""
    if not plain_token:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(plain_token.encode("utf-8")).decode("utf-8")

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt OAuth token retrieved from database."""
    if not encrypted_token:
        return ""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to decrypt token: {e}")

# JWT Authentication
security_bearer = HTTPBearer(auto_error=False)
cookie_sec = APIKeyCookie(name="auth_token", auto_error=False)

def create_access_token(data: dict, expires_days: int = settings.JWT_EXPIRE_DAYS) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)
    to_encode.update({"exp": expire, "iat": datetime.datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def verify_jwt_token(
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    cookie_token: Optional[str] = Depends(cookie_sec)
) -> dict:
    """Extract JWT token from Authorization header or Cookie and verify signature."""
    token = None
    if bearer and bearer.credentials:
        token = bearer.credentials
    elif cookie_token:
        token = cookie_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )
