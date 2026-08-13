from fastapi import APIRouter, HTTPException, status, Response, Depends
from app.config import settings
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token, verify_jwt_token

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, response: Response):
    """
    Authenticate with shared credentials (username/password).
    Returns long-lived JWT (30+ days) and sets HTTP-Only secure cookie.
    """
    if login_data.username != settings.SHARED_USERNAME or login_data.password != settings.SHARED_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    access_token = create_access_token(
        data={"sub": login_data.username, "role": "admin"},
        expires_days=settings.JWT_EXPIRE_DAYS
    )

    # Set HTTP-Only Cookie with 35-day max-age
    max_age_seconds = settings.JWT_EXPIRE_DAYS * 24 * 60 * 60
    response.set_cookie(
        key="auth_token",
        value=access_token,
        max_age=max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=False  # Set to True when using HTTPS in production
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_days=settings.JWT_EXPIRE_DAYS
    )

@router.get("/me", response_model=UserOut)
def get_current_user(current_user: dict = Depends(verify_jwt_token)):
    """Validates active JWT token session."""
    return UserOut(
        username=current_user.get("sub", settings.SHARED_USERNAME),
        is_authenticated=True
    )

@router.post("/logout")
def logout(response: Response):
    """Clears the authentication cookie."""
    response.delete_cookie(key="auth_token")
    return {"message": "Successfully logged out"}
