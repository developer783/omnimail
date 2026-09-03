import base64
import datetime
import logging
from typing import Optional, Tuple, Dict, Any
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ConnectedAccount, Email, KeywordFilter, EmailAttachment
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
    is_expired = False
    if account.token_expiry and (account.token_expiry - now).total_seconds() < 120:
        is_expired = True

    if not is_expired and decrypted_access_token and not decrypted_access_token.startswith("demo_"):
        return decrypted_access_token

    if decrypted_access_token and decrypted_access_token.startswith("demo_"):
        return decrypted_access_token

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


import re

def _linkify_plain_text(text_content: str) -> str:
    """
    Escapes HTML entities and converts raw URLs and email addresses into clickable <a href="..."> links,
    matching Gmail's native plain-text email reading pane behavior.
    """
    escaped = (
        text_content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    url_pattern = re.compile(
        r'(?P<url>(?:https?://|www\.)[^\s<>"\'\(\)]+?(?=[.,;:\?\)]?(?:\s|$)))',
        re.IGNORECASE
    )
    def replace_url(m):
        u = m.group("url")
        href = u if u.lower().startswith("http") else f"http://{u}"
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: underline;">{u}</a>'

    linkified = url_pattern.sub(replace_url, escaped)
    email_pattern = re.compile(
        r'(?P<email>\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)',
        re.IGNORECASE
    )
    def replace_email(m):
        e = m.group("email")
        return f'<a href="mailto:{e}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: underline;">{e}</a>'

    return email_pattern.sub(replace_email, linkified)


def _get_header_val(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_body_and_attachments(db: Session, account: ConnectedAccount, gmail_msg_id: str, payload: Dict[str, Any]) -> Tuple[str, list]:
    html_body = ""
    text_body = ""
    inline_cids: Dict[str, str] = {}
    attachments: list = []

    def _walk_parts(part: Dict[str, Any]):
        nonlocal html_body, text_body, inline_cids, attachments
        filename = part.get("filename", "")
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        body_data = body.get("data", "")
        attachment_id = body.get("attachmentId", "")
        size_bytes = body.get("size", 0)

        headers = part.get("headers", [])
        content_id = _get_header_val(headers, "Content-ID") or _get_header_val(headers, "Content-Id") or _get_header_val(headers, "X-Attachment-Id")
        clean_cid = content_id.strip("<>").strip()

        # Extract inline CID image
        if clean_cid:
            b64_str = body_data
            if not b64_str and attachment_id:
                try:
                    file_bytes = download_attachment_data(db, account, gmail_msg_id, attachment_id)
                    b64_str = base64.urlsafe_b64encode(file_bytes).decode("utf-8")
                except Exception as e:
                    logger.warning(f"Could not fetch inline CID image bytes for '{clean_cid}': {e}")

            if b64_str:
                pad = len(b64_str) % 4
                if pad:
                    b64_str += "=" * (4 - pad)
                std_b64 = b64_str.replace("-", "+").replace("_", "/")
                data_uri = f"data:{mime_type or 'image/png'};base64,{std_b64}"
                inline_cids[clean_cid] = data_uri

        # Extract true downloadable attachments (not CID inline images)
        if (filename and attachment_id and not clean_cid) or (filename and size_bytes > 0 and attachment_id and not clean_cid):
            attachments.append({
                "filename": filename,
                "mime_type": mime_type or "application/octet-stream",
                "attachment_id": attachment_id,
                "size_bytes": size_bytes
            })
        elif attachment_id and not filename and not clean_cid:
            synthetic_filename = f"attachment_{len(attachments)+1}"
            attachments.append({
                "filename": synthetic_filename,
                "mime_type": mime_type or "application/octet-stream",
                "attachment_id": attachment_id,
                "size_bytes": size_bytes
            })
        elif not clean_cid and not attachment_id:
            if mime_type == "text/html" and body_data and not html_body:
                html_body = _decode_body_data(body_data)
            elif mime_type == "text/plain" and body_data and not text_body:
                text_body = _decode_body_data(body_data)

        parts = part.get("parts", [])
        for sub_part in parts:
            _walk_parts(sub_part)

    _walk_parts(payload)

    final_body = ""
    if html_body.strip():
        final_body = html_body
    elif text_body.strip():
        linkified_text = _linkify_plain_text(text_body)
        final_body = f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; line-height: 1.6; color: #222; padding: 16px;"><pre style="white-space: pre-wrap; word-wrap: break-word;">{linkified_text}</pre></div>'
    else:
        final_body = '<div style="font-family: sans-serif; color: #888; padding: 20px;"><em>(No body content available)</em></div>'

    # Replace all cid: Content-ID references in HTML body with Data URIs
    for cid, data_uri in inline_cids.items():
        final_body = final_body.replace(f"cid:{cid}", data_uri)
        final_body = final_body.replace(f"cid:<{cid}>", data_uri)
        final_body = final_body.replace(f"cid:%3C{cid}%3E", data_uri)

    # Inject <base target="_blank"> so all links inside iframe open in new tab
    if "<head>" in final_body.lower():
        idx = final_body.lower().find("<head>") + 6
        final_body = final_body[:idx] + '<base target="_blank">' + final_body[idx:]
    elif "<html>" in final_body.lower():
        idx = final_body.lower().find("<html>") + 6
        final_body = final_body[:idx] + '<head><base target="_blank"></head>' + final_body[idx:]
    else:
        final_body = '<base target="_blank">' + final_body

    return final_body, attachments


def download_attachment_data(db: Session, account: ConnectedAccount, gmail_message_id: str, attachment_id: str) -> bytes:
    """Fetch base64 attachment payload on-demand from Gmail API."""
    access_token = get_valid_access_token(db, account)
    headers = {"Authorization": f"Bearer {access_token}"}
    
    url = f"{GMAIL_API_BASE}/messages/{gmail_message_id}/attachments/{attachment_id}"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"Failed to download attachment from Gmail API: {resp.status_code} - {resp.text}")
        
        data_b64 = resp.json().get("data", "")
        if not data_b64:
            return b""
        
        pad = len(data_b64) % 4
        if pad:
            data_b64 += "=" * (4 - pad)
        return base64.urlsafe_b64decode(data_b64)


def _parse_header(headers: list, name: str, default: str = "") -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", default)
    return default


def send_gmail_mime_message(db: Session, account: ConnectedAccount, raw_mime_bytes: bytes, thread_id: Optional[str] = None) -> dict:
    access_token = get_valid_access_token(db, account)
    if access_token.startswith("demo_"):
        return {"id": f"sent_demo_{int(datetime.datetime.utcnow().timestamp())}", "threadId": thread_id or "demo_thread"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

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
    If keyword filters exist in DB, incorporates them into Gmail API query AND performs second-pass exact substring checks.
    Persists only matching messages with received_at >= now - 24 hours.
    Returns number of newly inserted emails.
    """
    logger.info(f"[Backfill Job Start] Starting email fetch for account_id={account.id} ({account.google_email})")
    account.sync_status = "syncing"
    db.commit()

    cutoff_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

    # 0. Fetch active global keyword filters
    active_filters = db.query(KeywordFilter).all()
    base_q = "newer_than:1d"

    if active_filters:
        kw_terms = []
        for f in active_filters:
            kw = f.keyword.strip()
            if not kw:
                continue
            clean_kw = kw.replace('"', '\\"')
            if f.field == "subject":
                kw_terms.append(f'subject:("{clean_kw}")')
            elif f.field == "sender":
                kw_terms.append(f'from:("{clean_kw}")')
            else:
                kw_terms.append(f'"{clean_kw}"')

        if kw_terms:
            or_clause = " OR ".join(kw_terms)
            base_q = f"newer_than:1d ({or_clause})"

    try:
        access_token = get_valid_access_token(db, account)
        headers = {"Authorization": f"Bearer {access_token}"}

        if access_token.startswith("demo_"):
            account.sync_status = "success"
            account.last_synced_at = datetime.datetime.utcnow()
            account.error_message = None
            db.commit()
            return 0

        query_params = {"maxResults": max_results, "q": base_q}
        logger.info(f"[Backfill Job API Query] GET {GMAIL_API_BASE}/messages params={query_params}")

        with httpx.Client(timeout=30.0) as client:
            list_resp = client.get(
                f"{GMAIL_API_BASE}/messages",
                headers=headers,
                params=query_params
            )

            if list_resp.status_code == 403 and "insufficientPermissions" in list_resp.text:
                err_msg = "Re-authorization required for updated Gmail API scopes. Please click 'Add Account' to reconnect."
                logger.warning(f"[Backfill Job Scope Warning] Account {account.google_email} needs re-authorization: {list_resp.text}")
                account.sync_status = "needs_reauth"
                account.error_message = err_msg
                db.commit()
                return 0

            if "Mail service not enabled" in list_resp.text or "FAILED_PRECONDITION" in list_resp.text:
                logger.info(f"[Backfill Job Info] Non-mail Google account connected cleanly: '{account.google_email}' (No Gmail Inbox service on domain)")
                account.sync_status = "no_gmail"
                account.last_synced_at = datetime.datetime.utcnow()
                account.error_message = "Connected Google Account (No Gmail Inbox service on domain)"
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

            if not messages_data:
                account.sync_status = "success"
                account.last_synced_at = datetime.datetime.utcnow()
                account.error_message = None
                db.commit()
                return 0

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
                existing_ids.add(msg_id)

                detail_resp = client.get(
                    f"{GMAIL_API_BASE}/messages/{msg_id}",
                    headers=headers,
                    params={"format": "full"}
                )
                if detail_resp.status_code != 200:
                    logger.warning(f"Failed to fetch detail for msg {msg_id}: {detail_resp.status_code}")
                    continue

                msg_detail = detail_resp.json()
                label_ids = msg_detail.get("labelIds", [])
                thread_id = msg_detail.get("threadId") or msg_id
                payload = msg_detail.get("payload", {})
                msg_headers = payload.get("headers", [])

                internal_date_ms = msg_detail.get("internalDate")
                if internal_date_ms:
                    received_at = datetime.datetime.fromtimestamp(int(internal_date_ms) / 1000.0, tz=datetime.timezone.utc)
                else:
                    received_at = datetime.datetime.now(datetime.timezone.utc)

                raw_from = _parse_header(msg_headers, "From", default="Unknown Sender")
                raw_to = _parse_header(msg_headers, "To", default="")
                if not raw_to:
                    raw_to = _parse_header(msg_headers, "Cc", default="")

                is_sent_mail = (account.google_email and account.google_email.lower() in raw_from.lower()) or ("SENT" in label_ids and not ("mailer-daemon" in raw_from.lower() or "mail delivery subsystem" in raw_from.lower()))
                in_reply_to_hdr = _parse_header(msg_headers, "In-Reply-To", default="")
                references_hdr = _parse_header(msg_headers, "References", default="")

                if is_sent_mail and not ("mailer-daemon" in raw_from.lower() or "mail delivery subsystem" in raw_from.lower()):
                    sender = f"Me <{account.google_email}>"
                    recipient = raw_to if (raw_to and raw_to.strip() and raw_to.strip() not in ["Unknown Recipient", "Recipient"]) else account.google_email
                    
                    # Check if thread contains a prior inbound message in DB or has reply headers
                    has_prior_inbound = db.query(Email.id).filter(
                        Email.gmail_thread_id == thread_id,
                        Email.sender.notilike("Me %")
                    ).first() is not None

                    if has_prior_inbound or in_reply_to_hdr or references_hdr:
                        is_reply = True
                        folder_status = "replied"
                    else:
                        is_reply = False
                        folder_status = "sent"
                else:
                    sender = raw_from
                    recipient = raw_to if raw_to else account.google_email
                    is_reply = False
                    folder_status = "inbox"

                subject = _parse_header(msg_headers, "Subject", default="(No Subject)")
                message_id_hdr = _parse_header(msg_headers, "Message-ID", default=f"<{msg_id}@mail.gmail.com>")
                html_body, attachments_meta = _extract_body_and_attachments(db, account, msg_id, payload)

                # Second pass keyword verification if filters exist
                if active_filters:
                    matches_filter = False
                    for f in active_filters:
                        kw_lower = f.keyword.lower().strip()
                        if not kw_lower:
                            continue
                        if f.field == "subject" and kw_lower in subject.lower():
                            matches_filter = True
                            break
                        elif f.field == "sender" and kw_lower in sender.lower():
                            matches_filter = True
                            break
                        elif f.field == "body" and kw_lower in html_body.lower():
                            matches_filter = True
                            break
                        elif f.field == "any" and (kw_lower in subject.lower() or kw_lower in sender.lower() or kw_lower in html_body.lower()):
                            matches_filter = True
                            break

                    if not matches_filter:
                        logger.info(f"Skipping msg_id={msg_id}: does not match active keyword filters")
                        continue

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
                    fetched_at=datetime.datetime.now(datetime.timezone.utc),
                    is_reply=is_reply,
                    folder_status=folder_status
                )
                db.add(new_email)
                db.flush()

                for att_meta in attachments_meta:
                    att = EmailAttachment(
                        email_id=new_email.id,
                        filename=att_meta["filename"],
                        mime_type=att_meta["mime_type"],
                        gmail_attachment_id=att_meta["attachment_id"],
                        size_bytes=att_meta["size_bytes"]
                    )
                    db.add(att)

                new_emails_count += 1

            account.sync_status = "success"
            account.last_synced_at = datetime.datetime.utcnow()
            account.error_message = None
            db.commit()

            logger.info(f"[Backfill Job Complete] Account '{account.google_email}' (ID={account.id}): Inserted {new_emails_count} matching email(s) into database!")
            return new_emails_count

    except Exception as e:
        logger.error(f"[Backfill Job Error] Error fetching emails for {account.google_email}: {e}")
        account.sync_status = "error"
        account.error_message = str(e)
        db.commit()
        return 0
