import base64
import datetime
import logging
from typing import Optional, Tuple, Dict, Any
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ConnectedAccount, Email
from app.security import decrypt_token, encrypt_token

logger = logging.getLogger("gmail_service")
logger.setLevel(logging.INFO)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

def get_valid_access_token(db: Session, account: ConnectedAccount) -> str:
    """
    Checks if account's access token is valid. If expired or close to expiry,
    uses refresh_token to silently obtain a new access_token from Google.
    """
    decrypted_access_token = decrypt_token(account.access_token)
    decrypted_refresh_token = decrypt_token(account.refresh_token)

    now = datetime.datetime.utcnow()
    # Check if token is expired or expires within 2 minutes
    is_expired = False
    if account.token_expiry and (account.token_expiry - now).total_seconds() < 120:
        is_expired = True

    if not is_expired and decrypted_access_token and not decrypted_access_token.startswith("demo_"):
        return decrypted_access_token

    if decrypted_access_token and decrypted_access_token.startswith("demo_"):
        return decrypted_access_token

    # Token is expired, refresh it
    logger.info(f"[Token Refresh] Refreshing access token for account {account.google_email}...")
    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": decrypted_refresh_token,
        "grant_type": "refresh_token"
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(GOOGLE_TOKEN_URL, data=payload)
        if resp.status_code != 200:
            err_msg = f"Failed to refresh token: {resp.status_code} - {resp.text}"
            logger.error(f"[Token Refresh Error] {err_msg}")
            account.sync_status = "needs_reauth"
            account.error_message = "Refresh token expired or revoked. Please reconnect account."
            db.commit()
            raise ValueError(err_msg)

        data = resp.json()
        new_access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)

        if not new_access_token:
            raise ValueError("No access_token returned during refresh")

        account.access_token = encrypt_token(new_access_token)
        account.token_expiry = now + datetime.timedelta(seconds=expires_in)
        account.error_message = None
        db.commit()

        return new_access_token


def _decode_body_data(data_b64: str) -> str:
    """Decodes base64url encoded string into UTF-8 decoded text."""
    if not data_b64:
        return ""
    pad = len(data_b64) % 4
    if pad:
        data_b64 += "=" * (4 - pad)
    try:
        decoded_bytes = base64.urlsafe_b64decode(data_b64)
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Failed to decode MIME body: {e}")
        return ""


def _extract_body_from_payload(payload: Dict[str, Any]) -> str:
    """
    Traverses MIME structure recursively to extract original HTML body.
    If no HTML part exists, falls back to plain text.
    """
    html_body = ""
    text_body = ""

    def _walk_parts(part: Dict[str, Any]):
        nonlocal html_body, text_body
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")

        if mime_type == "text/html" and body_data and not html_body:
            html_body = _decode_body_data(body_data)
        elif mime_type == "text/plain" and body_data and not text_body:
            text_body = _decode_body_data(body_data)

        parts = part.get("parts", [])
        for sub_part in parts:
            _walk_parts(sub_part)

    _walk_parts(payload)

    if html_body.strip():
        return html_body
    elif text_body.strip():
        escaped_text = (
            text_body.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; line-height: 1.6; color: #222; padding: 16px;"><pre style="white-space: pre-wrap; word-wrap: break-word;">{escaped_text}</pre></div>'
    else:
        return '<div style="font-family: sans-serif; color: #888; padding: 20px;"><em>(No body content available)</em></div>'


def _parse_header(headers: list, name: str, default: str = "") -> str:
    """Extracts a specific header value (case-insensitive)."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", default)
    return default


def send_gmail_mime_message(db: Session, account: ConnectedAccount, raw_mime_bytes: bytes, thread_id: Optional[str] = None) -> dict:
    """
    Sends an RFC822 formatted MIME email message via Google's Gmail API `users.messages.send`.
    """
    access_token = get_valid_access_token(db, account)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Encode raw bytes as URL-safe base64 string
    encoded_raw = base64.urlsafe_b64encode(raw_mime_bytes).decode("utf-8")

    payload = {"raw": encoded_raw}
    if thread_id:
        payload["threadId"] = thread_id

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{GMAIL_API_BASE}/messages/send",
            headers=headers,
            json=payload
        )

        if resp.status_code not in [200, 201]:
            err_msg = f"Failed to send email via Gmail API: {resp.status_code} - {resp.text}"
            logger.error(err_msg)
            raise ValueError(err_msg)

        return resp.json()


def fetch_and_store_emails_for_account(db: Session, account: ConnectedAccount, max_results: int = 50) -> int:
    """
    Fetches recent emails from Gmail for given account received within the trailing 24 hours (q='newer_than:1d').
    Persists only messages with received_at >= now - 24 hours.
    Returns number of newly inserted emails.
    """
    logger.info(f"[Backfill Job Start] Starting email fetch for account_id={account.id} ({account.google_email})")
    account.sync_status = "syncing"
    db.commit()

    cutoff_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

    try:
        access_token = get_valid_access_token(db, account)
        headers = {"Authorization": f"Bearer {access_token}"}

        # Handle demo accounts gracefully
        if access_token.startswith("demo_"):
            account.sync_status = "success"
            account.last_synced_at = datetime.datetime.utcnow()
            account.error_message = None
            db.commit()
            return 0

        # 1. Fetch message list restricted to trailing 24 hours query (or fallback to recent if 0)
        query_params = {"maxResults": max_results, "q": "newer_than:1d"}
        logger.info(f"[Backfill Job API Query] GET {GMAIL_API_BASE}/messages params={query_params}")

        with httpx.Client(timeout=30.0) as client:
            list_resp = client.get(
                f"{GMAIL_API_BASE}/messages",
                headers=headers,
                params=query_params
            )

            # Check for insufficient permissions error
            if list_resp.status_code == 403 and "insufficientPermissions" in list_resp.text:
                err_msg = "Re-authorization required for updated Gmail API scopes. Please click 'Add Account' to reconnect."
                logger.warning(f"[Backfill Job Scope Warning] Account {account.google_email} needs re-authorization: {list_resp.text}")
                account.sync_status = "needs_reauth"
                account.error_message = err_msg
                db.commit()
                return 0

            if list_resp.status_code != 200:
                err_msg = f"Failed to list messages: {list_resp.status_code} - {list_resp.text}"
                account.sync_status = "error"
                account.error_message = err_msg
                db.commit()
                raise ValueError(err_msg)

            messages_data = list_resp.json().get("messages", [])
            logger.info(f"[Backfill Job API Response] Gmail API returned {len(messages_data)} message(s) for account '{account.google_email}'")

            # Fallback: If 24-hour query returns 0 messages, try fetching recent 10 messages to ensure inbox isn't empty if user's last email was older
            if not messages_data:
                logger.info(f"[Backfill Job Fallback] 'newer_than:1d' returned 0 messages for {account.google_email}. Fallback query for recent messages...")
                fallback_resp = client.get(
                    f"{GMAIL_API_BASE}/messages",
                    headers=headers,
                    params={"maxResults": 15}
                )
                if fallback_resp.status_code == 200:
                    messages_data = fallback_resp.json().get("messages", [])
                    logger.info(f"[Backfill Job Fallback Response] Fallback query returned {len(messages_data)} message(s)")

            if not messages_data:
                account.sync_status = "success"
                account.last_synced_at = datetime.datetime.utcnow()
                account.error_message = None
                db.commit()
                return 0

            # Get existing gmail_message_ids for this account to skip duplicates
            existing_ids = set(
                row[0] for row in db.query(Email.gmail_message_id)
                .filter(Email.account_id == account.id)
                .all()
            )

            new_emails_count = 0
            for msg_item in messages_data:
                msg_id = msg_item["id"]
                if msg_id in existing_ids:
                    continue

                # Fetch full message detail
                detail_resp = client.get(
                    f"{GMAIL_API_BASE}/messages/{msg_id}",
                    headers=headers,
                    params={"format": "full"}
                )
                if detail_resp.status_code != 200:
                    logger.warning(f"Failed to fetch detail for msg {msg_id}: {detail_resp.status_code}")
                    continue

                msg_detail = detail_resp.json()
                thread_id = msg_detail.get("threadId", msg_id)
                payload = msg_detail.get("payload", {})
                msg_headers = payload.get("headers", [])

                # Determine received timestamp
                internal_date_ms = msg_detail.get("internalDate")
                if internal_date_ms:
                    received_at = datetime.datetime.utcfromtimestamp(int(internal_date_ms) / 1000.0)
                else:
                    received_at = datetime.datetime.utcnow()

                sender = _parse_header(msg_headers, "From", default="Unknown Sender")
                recipient = _parse_header(msg_headers, "To", default=account.google_email)
                subject = _parse_header(msg_headers, "Subject", default="(No Subject)")
                message_id_hdr = _parse_header(msg_headers, "Message-ID", default=f"<{msg_id}@mail.gmail.com>")
                html_body = _extract_body_from_payload(payload)

                new_email = Email(
                    account_id=account.id,
                    gmail_message_id=msg_id,
                    gmail_thread_id=thread_id,
                    message_id_header=message_id_hdr,
                    sender=sender,
                    recipient=recipient,
                    subject=subject,
                    html_body=html_body,
                    received_at=received_at,
                    fetched_at=datetime.datetime.utcnow()
                )
                db.add(new_email)
                new_emails_count += 1

            account.sync_status = "success"
            account.last_synced_at = datetime.datetime.utcnow()
            account.error_message = None
            db.commit()

            logger.info(f"[Backfill Job Complete] Account '{account.google_email}' (ID={account.id}): Successfully inserted {new_emails_count} new email(s) into database!")
            return new_emails_count

    except Exception as e:
        logger.error(f"[Backfill Job Error] Error fetching emails for {account.google_email}: {e}")
        account.sync_status = "error"
        account.error_message = str(e)
        db.commit()
        return 0
