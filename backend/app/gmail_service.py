import base64
import datetime
import html
import logging
import re
import threading
import time
import urllib.parse
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

# Held for the duration of a full all-accounts sync run (scheduled or manual), so runs never
# overlap and peak memory stays bounded.
sync_lock = threading.Lock()

# Per-account locks: an account is never synced twice at once (e.g. the OAuth backfill racing
# a scheduled run), which would otherwise duplicate work and collide on inserts.
_account_locks: Dict[int, threading.Lock] = {}
_account_locks_guard = threading.Lock()


def _account_lock(account_id: int) -> threading.Lock:
    with _account_locks_guard:
        return _account_locks.setdefault(account_id, threading.Lock())

# Inline images whose bytes Gmail already includes in the message payload are embedded as
# data: URIs only when small; anything else is served on demand by GET /emails/inline/...
MAX_EMBEDDED_INLINE_B64 = 64 * 1024

_DATA_URI_RE = None
_TAG_RE = None


def make_snippet(html_body: str, limit: int = 200) -> str:
    """Plain-text preview of an HTML body, for list views."""
    global _TAG_RE
    if not html_body:
        return ""
    if _TAG_RE is None:
        _TAG_RE = re.compile(r"<(style|script)[^>]*>.*?</\1>|<!--.*?-->|<[^>]+>", re.IGNORECASE | re.DOTALL)
    text = html.unescape(_TAG_RE.sub(" ", html_body[:200_000]))
    return " ".join(text.split())[:limit]


def _cap_body_size(body: str) -> str:
    """Strip embedded data: URIs from bodies that exceed the storage cap."""
    global _DATA_URI_RE
    if len(body) <= settings.MAX_STORED_BODY_BYTES:
        return body
    if _DATA_URI_RE is None:
        _DATA_URI_RE = re.compile(r"data:[a-z0-9.+/-]+;base64,[A-Za-z0-9+/=_-]+", re.IGNORECASE)
    return _DATA_URI_RE.sub("", body)

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



_LINK_RE = re.compile(
    r"(?P<url>(?:https?://|\bwww\.)[^\s<>\"']+)"
    r"|(?P<email>\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)",
    re.IGNORECASE
)


def _trim_url(url: str) -> str:
    """Drops sentence punctuation and closing brackets that weren't opened inside the URL."""
    pairs = {")": "(", "]": "[", "}": "{"}
    while url:
        last = url[-1]
        if last in ".,;:!?*" or (last in pairs and url.count(last) > url.count(pairs[last])):
            url = url[:-1]
        else:
            break
    return url


def _linkify_plain_text(text_content: str) -> str:
    """
    Escapes HTML entities and converts raw URLs and email addresses into clickable <a href="..."> links,
    matching Gmail's native plain-text email reading pane behavior.
    """
    # One pass over the raw text, escaping each piece as it is emitted. Escaping first made URLs
    # swallow "&gt;", and a second pass for addresses corrupted URLs that contain an email address.
    out = []
    pos = 0
    for m in _LINK_RE.finditer(text_content):
        if m.group("url"):
            label = _trim_url(m.group("url"))
            href = label if label.lower().startswith("http") else f"https://{label}"
        else:
            label = m.group("email")
            href = f"mailto:{label}"
        out.append(html.escape(text_content[pos:m.start()], quote=False))
        out.append(
            f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer" '
            f'style="color: #2563eb; text-decoration: underline;">{html.escape(label, quote=False)}</a>'
        )
        pos = m.start() + len(label)
    out.append(html.escape(text_content[pos:], quote=False))
    return "".join(out)


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
    cid_parts: list = []

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

        # A body part is text without a filename, wherever its data lives: some senders put a
        # Content-ID on the body, and Gmail moves large bodies into a separate attachment.
        if mime_type in ("text/html", "text/plain") and not filename and (body_data or attachment_id):
            already_have = html_body if mime_type == "text/html" else text_body
            if already_have:
                return
            if body_data:
                decoded = _decode_body_data(body_data)
            else:
                # A failure propagates, so the message is retried next sync instead of being
                # stored permanently without its body.
                decoded = download_attachment_data(db, account, gmail_msg_id, attachment_id).decode("utf-8", errors="replace")
            if mime_type == "text/html":
                html_body = decoded
            else:
                text_body = decoded
            return

        # Parts with a Content-ID may be inline images or ordinary files (Gmail puts one on every
        # attachment); which one is only known once the whole body has been read.
        if clean_cid:
            cid_parts.append((clean_cid, filename, mime_type, body_data, attachment_id, size_bytes))

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

    body_refs = urllib.parse.unquote(html.unescape(html_body)).lower() if cid_parts else ""
    for cid, filename, mime_type, body_data, attachment_id, size_bytes in cid_parts:
        is_referenced = re.search(rf"cid:<?{re.escape(cid.lower())}(?![\w.@+-])", body_refs) is not None
        if is_referenced and mime_type.startswith("image/"):
            # Small images already present in the payload are embedded; larger ones are referenced
            # by URL and fetched from Gmail only when the email is viewed, instead of being
            # downloaded during sync and stored base64-encoded in the email body.
            if body_data and len(body_data) <= MAX_EMBEDDED_INLINE_B64:
                std_b64 = body_data.replace("-", "+").replace("_", "/")
                std_b64 += "=" * (-len(std_b64) % 4)
                inline_cids[cid] = f"data:{mime_type};base64,{std_b64}"
            elif attachment_id:
                inline_cids[cid] = (
                    f"/emails/inline/{urllib.parse.quote(gmail_msg_id, safe='')}/"
                    f"{urllib.parse.quote(attachment_id, safe='')}"
                    f"?mime={urllib.parse.quote(mime_type, safe='')}"
                )
        elif attachment_id:
            attachments.append({
                "filename": filename or f"attachment_{len(attachments)+1}",
                "mime_type": mime_type or "application/octet-stream",
                "attachment_id": attachment_id,
                "size_bytes": size_bytes
            })

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

    return _cap_body_size(final_body), attachments


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


NO_BODY_MARKER = "(No body content available)"


def is_damaged_body(body: str) -> bool:
    """True for bodies stored by older syncs that lost their content or corrupted their links."""
    body = body or ""
    return (
        NO_BODY_MARKER in body
        or '<a href="mailto:' in body and re.search(r'href="[^"]*<a href=', body) is not None
        or re.search(r'href="[^"]*&gt"', body) is not None
    )


def refresh_stored_email(db: Session, account: ConnectedAccount, email: Email) -> None:
    """
    Re-reads an email from Gmail: adds attachments an older sync missed (existing rows keep their
    ids) and replaces the body if it was damaged. Does nothing if Gmail can't be reached.
    """
    access_token = get_valid_access_token(db, account)
    if access_token.startswith("demo_"):
        return
    with httpx.Client(timeout=20.0) as client:
        resp = _gmail_get(
            client, f"{GMAIL_API_BASE}/messages/{email.gmail_message_id}",
            {"Authorization": f"Bearer {access_token}"}, {"format": "full"}, attempts=1
        )
    if resp.status_code == 404:
        # Deleted in Gmail: nothing more to recover, so don't ask again
        email.attachments_checked = True
        db.commit()
        return
    if resp.status_code != 200:
        return

    body, attachments_meta = _extract_body_and_attachments(db, account, email.gmail_message_id, resp.json().get("payload", {}))
    if is_damaged_body(email.html_body) and not is_damaged_body(body):
        email.html_body = body
        email.snippet = email.snippet or make_snippet(body)

    known = {}
    for att in email.attachments:
        key = (att.filename, att.size_bytes)
        known[key] = known.get(key, 0) + 1
    for m in attachments_meta:
        key = (m["filename"][:512], m["size_bytes"] or 0)
        if known.get(key, 0) > 0:
            known[key] -= 1
            continue
        email.attachments.append(EmailAttachment(
            filename=key[0], mime_type=m["mime_type"][:255],
            gmail_attachment_id=m["attachment_id"], size_bytes=key[1]
        ))
    email.attachments_checked = True
    db.commit()


def _gmail_get(client: httpx.Client, url: str, headers: dict, params: dict, attempts: int = 3) -> httpx.Response:
    """GET against the Gmail API, retrying rate-limit (429) and transient 5xx responses."""
    for attempt in range(attempts):
        try:
            resp = client.get(url, headers=headers, params=params)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            time.sleep(1 + attempt * 2)
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            time.sleep(1 + attempt * 2)
            continue
        return resp
    return resp


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


def fetch_and_store_emails_for_account(db: Session, account: ConnectedAccount, max_results: Optional[int] = None) -> int:
    with _account_lock(account.id):
        return _fetch_and_store_emails_for_account(db, account, max_results or settings.SYNC_MAX_RESULTS)


def _fetch_and_store_emails_for_account(db: Session, account: ConnectedAccount, max_results: int) -> int:
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

        with httpx.Client(timeout=30.0) as client:
            # Page through every message in the 24h window. Busy mailboxes receive far more than
            # one page a day, and only looking at the newest page silently skipped the rest.
            message_ids = []
            page_token = None
            while True:
                query_params = {"maxResults": 100, "q": base_q}
                if page_token:
                    query_params["pageToken"] = page_token
                list_resp = _gmail_get(client, f"{GMAIL_API_BASE}/messages", headers, query_params)

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
                    raise ValueError(f"Failed to list messages: {list_resp.status_code} - {list_resp.text[:500]}")

                list_data = list_resp.json()
                message_ids.extend(m["id"] for m in list_data.get("messages", []))
                page_token = list_data.get("nextPageToken")
                if not page_token or len(message_ids) >= settings.SYNC_MAX_LISTED:
                    break

            logger.info(f"[Backfill Job API Response] Gmail API returned {len(message_ids)} message(s) in the last 24h for account '{account.google_email}'")

            if not message_ids:
                account.sync_status = "success"
                account.last_synced_at = datetime.datetime.utcnow()
                account.error_message = None
                db.commit()
                return 0

            # Only look up the listed ids, not every id ever stored for the account
            existing_ids = set()
            for i in range(0, len(message_ids), 500):
                chunk = message_ids[i:i + 500]
                existing_ids.update(
                    row[0] for row in db.query(Email.gmail_message_id)
                    .filter(Email.account_id == account.id, Email.gmail_message_id.in_(chunk))
                    .all()
                )

            new_emails_count = 0
            failed_count = 0
            # Newest first; anything beyond this run's cap is picked up by the next run
            for msg_id in message_ids:
                if new_emails_count >= max_results:
                    break
                if msg_id in existing_ids:
                    continue
                existing_ids.add(msg_id)

                detail_resp = _gmail_get(client, f"{GMAIL_API_BASE}/messages/{msg_id}", headers, {"format": "full"})
                if detail_resp.status_code != 200:
                    logger.warning(f"Failed to fetch detail for msg {msg_id}: {detail_resp.status_code}")
                    failed_count += 1
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
                gmail_snippet = html.unescape(msg_detail.get("snippet", "") or "")
                message_id_hdr = _parse_header(msg_headers, "Message-ID", default=f"<{msg_id}@mail.gmail.com>")
                try:
                    html_body, attachments_meta = _extract_body_and_attachments(db, account, msg_id, payload)
                except Exception as e:
                    logger.error(f"[Backfill Job] Skipping msg_id={msg_id} for {account.google_email}: could not read body: {e}")
                    failed_count += 1
                    continue

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
                    gmail_thread_id=thread_id[:255],
                    # Headers are trimmed to their column sizes: Postgres rejects longer values, and
                    # bulk mail often has To/Cc lists far longer than the 512-char column.
                    message_id_header=message_id_hdr[:512],
                    sender=sender[:512],
                    recipient=recipient[:512] if recipient else recipient,
                    subject=subject[:1024],
                    html_body=html_body,
                    snippet=(gmail_snippet or make_snippet(html_body))[:300],
                    received_at=received_at,
                    fetched_at=datetime.datetime.now(datetime.timezone.utc),
                    is_reply=is_reply,
                    attachments_checked=True,
                    folder_status=folder_status
                )
                # Each message is saved in its own savepoint: one message the database rejects
                # is skipped and logged instead of aborting (and rolling back) the account's sync.
                try:
                    with db.begin_nested():
                        db.add(new_email)
                        db.flush()
                        for att_meta in attachments_meta:
                            db.add(EmailAttachment(
                                email_id=new_email.id,
                                filename=(att_meta["filename"] or "attachment")[:512],
                                mime_type=(att_meta["mime_type"] or "application/octet-stream")[:255],
                                gmail_attachment_id=att_meta["attachment_id"],
                                size_bytes=att_meta["size_bytes"] or 0
                            ))
                except Exception as e:
                    logger.error(f"[Backfill Job] Skipping msg_id={msg_id} for {account.google_email}: could not be saved: {e}")
                    failed_count += 1
                    continue

                new_emails_count += 1

                # Commit in small batches so fetched bodies don't pile up in the session until
                # the whole sync finishes; committed objects are released by the identity map.
                del msg_detail, payload, html_body
                if new_emails_count % settings.SYNC_COMMIT_BATCH == 0:
                    db.commit()

            account.sync_status = "success"
            account.last_synced_at = datetime.datetime.utcnow()
            account.error_message = None
            db.commit()

            logger.info(
                f"[Backfill Job Complete] Account '{account.google_email}' (ID={account.id}): "
                f"inserted {new_emails_count} email(s), {failed_count} failed (retried next run)."
            )
            return new_emails_count

    except Exception as e:
        logger.error(f"[Backfill Job Error] Error fetching emails for {account.google_email}: {e}")
        # Keep whatever was already committed, then record the error. Without the rollback, a
        # failed flush leaves the session unusable and this commit itself would raise.
        db.rollback()
        account.sync_status = "error"
        account.error_message = str(e)
        db.commit()
        return 0
