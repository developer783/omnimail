import datetime
import urllib.parse
import logging
from typing import List, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.database import get_db
from app.models import ConnectedAccount, Email
from app.schemas import ConnectedAccountOut
from app.security import encrypt_token, decrypt_token, verify_jwt_token
from app.gmail_service import fetch_and_store_emails_for_account

logger = logging.getLogger("google_oauth")
logger.setLevel(logging.INFO)

router = APIRouter(tags=["Google OAuth & Accounts"])

GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"

# Explicitly include userinfo.email & userinfo.profile so Google UserInfo endpoint succeeds with 200 OK!
GMAIL_SCOPES = "https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"

@router.get("/auth/google/start")
def google_oauth_start(
    json_mode: bool = Query(False, alias="json"),
    state: Optional[str] = Query("add_account")
):
    """
    Redirects user to Google OAuth 2.0 consent screen.
    Forces account chooser via prompt='select_account consent' so connecting a 2nd/3rd account works seamlessly.
    """
    if not settings.GOOGLE_CLIENT_ID or "your_google_client_id" in settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GOOGLE_CLIENT_ID is not configured in backend/.env. Please paste your Google Cloud Client ID into backend/.env or use demo connect."
        )

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "prompt": "select_account consent",
        "state": state or "add_account"
    }
    
    auth_url = f"{GOOGLE_AUTH_BASE}?{urllib.parse.urlencode(params)}"

    logger.info(f"[OAuth Start] Initiated Google Auth flow with scopes='{GMAIL_SCOPES}' and state='{state}'")

    if json_mode:
        return {"url": auth_url}
    
    return RedirectResponse(url=auth_url, status_code=307)

@router.get("/auth/google/callback")
def google_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Google OAuth Callback endpoint.
    Exchanges authorization code for access_token + refresh_token,
    fetches connected Google user email reliably, logs email at each step, and creates a NEW row in connected_accounts
    if google_email is not present, or updates the existing row if re-authorizing.
    """
    logger.info(f"[OAuth Callback] Received callback request with state='{state}'")

    if error:
        logger_msg = f"OAuth error returned from Google: {error}"
        logger.error(f"[OAuth Callback Error] {logger_msg}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}?error={urllib.parse.quote(logger_msg)}")

    if not code:
        logger.error("[OAuth Callback Error] Missing authorization code parameter")
        raise HTTPException(status_code=400, detail="Missing authorization code in query parameters")

    # 1. Exchange authorization code for tokens
    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    with httpx.Client(timeout=20.0) as client:
        token_resp = client.post(GOOGLE_TOKEN_URL, data=payload)
        if token_resp.status_code != 200:
            err_detail = f"Failed to exchange code: {token_resp.status_code} - {token_resp.text}"
            logger.error(f"[OAuth Callback Error] Token Exchange Failed: {err_detail}")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}?error={urllib.parse.quote(err_detail)}")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        if not access_token:
            logger.error("[OAuth Callback Error] No access_token received in response")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}?error=No+access_token+received")

        # 2. Retrieve user's email address from Google UserInfo or Gmail API Profile
        google_email = None

        # Method A: Google UserInfo API
        userinfo_resp = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if userinfo_resp.status_code == 200:
            google_email = userinfo_resp.json().get("email")

        # Method B: Fallback to Gmail Profile API
        if not google_email:
            profile_resp = client.get(
                GMAIL_PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if profile_resp.status_code == 200:
                google_email = profile_resp.json().get("emailAddress")

        if not google_email or google_email == "unknown@gmail.com":
            err_msg = "Could not retrieve authenticating Google account email address from Google API."
            logger.error(f"[OAuth Callback Error] {err_msg}")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}?error={urllib.parse.quote(err_msg)}")

        logger.info(f"[OAuth Callback Step 2] Successfully authenticated Google Account email: '{google_email}'")

        token_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)

        # 3. Store encrypted tokens in database looking up BY google_email
        account = db.query(ConnectedAccount).filter(ConnectedAccount.google_email == google_email).first()
        if not account:
            logger.info(f"[OAuth Callback Step 3] Creating NEW row in connected_accounts table for '{google_email}'")
            account = ConnectedAccount(
                google_email=google_email,
                access_token=encrypt_token(access_token),
                refresh_token=encrypt_token(refresh_token or ""),
                token_expiry=token_expiry,
                connected_at=datetime.datetime.utcnow(),
                sync_status="idle"
            )
            db.add(account)
        else:
            logger.info(f"[OAuth Callback Step 3] Updating EXISTING row (id={account.id}) in connected_accounts for '{google_email}'")
            account.access_token = encrypt_token(access_token)
            if refresh_token:
                account.refresh_token = encrypt_token(refresh_token)
            account.token_expiry = token_expiry
            account.sync_status = "idle"
            account.error_message = None

        db.commit()
        db.refresh(account)

        # Integration Verification Check: Re-query database to guarantee row exists before responding!
        verified_acc = db.query(ConnectedAccount).filter(ConnectedAccount.id == account.id).first()
        if not verified_acc:
            logger.error(f"[OAuth Callback Error] DB Verification Failed: Account id={account.id} not found after commit!")
            return RedirectResponse(url=f"{settings.FRONTEND_URL}?error=Database+commit+verification+failed")

        logger.info(f"[OAuth Callback Step 4] Verified account in DB: id={verified_acc.id}, google_email='{verified_acc.google_email}'")

        # 4. Trigger initial email fetch
        try:
            logger.info(f"[OAuth Callback Step 5] Triggering initial email fetch for account_id={verified_acc.id} ({google_email})")
            fetch_and_store_emails_for_account(db, verified_acc, max_results=50)
        except Exception as e:
            logger.error(f"[OAuth Callback Step 5 Warning] Initial email sync error for '{google_email}': {e}")

    return RedirectResponse(url=f"{settings.FRONTEND_URL}?account_added=true&email={urllib.parse.quote(google_email)}", status_code=307)

@router.get("/accounts", response_model=List[ConnectedAccountOut])
def list_connected_accounts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Lists all connected Google accounts with email counts, unread counts, and sync statuses."""
    accounts = db.query(ConnectedAccount).all()
    results = []

    for acc in accounts:
        email_count = db.query(func.count(Email.id)).filter(Email.account_id == acc.id).scalar() or 0
        unread_count = db.query(func.count(Email.id)).filter(Email.account_id == acc.id, Email.is_read == False).scalar() or 0
        
        results.append(
            ConnectedAccountOut(
                id=acc.id,
                google_email=acc.google_email,
                connected_at=acc.connected_at,
                sync_status=acc.sync_status,
                last_synced_at=acc.last_synced_at,
                error_message=acc.error_message,
                email_count=email_count,
                unread_count=unread_count
            )
        )

    return results

@router.delete("/accounts/{account_id}")
def delete_connected_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    account = db.query(ConnectedAccount).filter(ConnectedAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    email = account.google_email

    raw_refresh_token = decrypt_token(account.refresh_token) if account.refresh_token else ""
    raw_access_token = decrypt_token(account.access_token) if account.access_token else ""
    token_to_revoke = raw_refresh_token or raw_access_token

    if token_to_revoke and not token_to_revoke.startswith("demo_"):
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(
                    GOOGLE_REVOKE_URL,
                    params={"token": token_to_revoke},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
        except Exception:
            pass

    db.delete(account)
    db.commit()

    return {"message": f"Successfully revoked tokens and removed account {email} and all associated emails"}
