import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.models import ConnectedAccount, Email
from app.schemas import (
    EmailOut, EmailListResponse, SyncResponse, FolderCounts, EmailUpdate,
    EmailReplyRequest, EmailForwardRequest
)
from app.security import verify_jwt_token
from app.gmail_service import fetch_and_store_emails_for_account, send_gmail_mime_message
from app.routers.google_oauth import list_connected_accounts

router = APIRouter(prefix="/emails", tags=["Emails"])

@router.get("", response_model=EmailListResponse)
def get_emails(
    account_id: Optional[int] = Query(None, description="Filter by connected account ID"),
    folder: Optional[str] = Query("inbox", description="Folder filter: inbox, unread, starred, follow_up, replied, snoozed, or all"),
    q: Optional[str] = Query(None, description="Search term for subject, sender, or keywords"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Unified Inbox endpoint.
    Returns emails filtered by folder, account_id, and search query.
    Also returns global folder counts for the sidebar badges.
    """
    base_query = db.query(Email, ConnectedAccount.google_email).join(
        ConnectedAccount, Email.account_id == ConnectedAccount.id
    )

    cutoff_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    # Enforce rolling 24-hour retention filter for inbound emails (preserve sent replies)
    base_query = base_query.filter(
        (Email.received_at >= cutoff_24h) | (Email.folder_status == "replied") | (Email.sender.ilike("Me %"))
    )

    if account_id:
        base_query = base_query.filter(Email.account_id == account_id)

    # Apply folder filter
    filtered_query = base_query
    if folder == "unread":
        filtered_query = filtered_query.filter(Email.is_read == False)
    elif folder == "starred":
        filtered_query = filtered_query.filter(Email.is_starred == True)
    elif folder in ["follow_up", "replied", "snoozed"]:
        filtered_query = filtered_query.filter(Email.folder_status == folder)
    elif folder == "inbox":
        filtered_query = filtered_query.filter(Email.folder_status == "inbox")

    # Apply global search if present
    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        filtered_query = filtered_query.filter(
            (Email.subject.ilike(search_pattern)) | 
            (Email.sender.ilike(search_pattern)) | 
            (Email.html_body.ilike(search_pattern))
        )

    total_count = filtered_query.count()
    results = filtered_query.order_by(desc(Email.received_at)).offset(offset).limit(limit).all()

    email_out_items = []
    for email_obj, account_email in results:
        email_out_items.append(
            EmailOut(
                id=email_obj.id,
                account_id=email_obj.account_id,
                account_email=account_email,
                gmail_message_id=email_obj.gmail_message_id,
                gmail_thread_id=email_obj.gmail_thread_id,
                message_id_header=email_obj.message_id_header,
                sender=email_obj.sender,
                recipient=email_obj.recipient,
                subject=email_obj.subject,
                html_body=email_obj.html_body,
                received_at=email_obj.received_at,
                fetched_at=email_obj.fetched_at,
                is_read=email_obj.is_read,
                is_starred=email_obj.is_starred,
                folder_status=email_obj.folder_status
            )
        )

    # Calculate Folder Counts across current context (or global)
    cnt_query = db.query(Email)
    if account_id:
        cnt_query = cnt_query.filter(Email.account_id == account_id)

    inbox_cnt = cnt_query.filter(Email.folder_status == "inbox").count()
    unread_cnt = cnt_query.filter(Email.is_read == False).count()
    starred_cnt = cnt_query.filter(Email.is_starred == True).count()
    follow_up_cnt = cnt_query.filter(Email.folder_status == "follow_up").count()
    replied_cnt = cnt_query.filter(Email.folder_status == "replied").count()
    snoozed_cnt = cnt_query.filter(Email.folder_status == "snoozed").count()

    folder_counts = FolderCounts(
        inbox=inbox_cnt,
        unread=unread_cnt,
        starred=starred_cnt,
        follow_up=follow_up_cnt,
        replied=replied_cnt,
        snoozed=snoozed_cnt
    )

    accounts_meta = list_connected_accounts(db=db, current_user=current_user)

    return EmailListResponse(
        items=email_out_items,
        total=total_count,
        accounts=accounts_meta,
        folder_counts=folder_counts
    )

@router.get("/{email_id}", response_model=EmailOut)
def get_email_by_id(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Fetch single email detailed record."""
    res = db.query(Email, ConnectedAccount.google_email).join(
        ConnectedAccount, Email.account_id == ConnectedAccount.id
    ).filter(Email.id == email_id).first()

    if not res:
        raise HTTPException(status_code=404, detail="Email not found")

    email_obj, account_email = res

    # Mark as read upon viewing
    if not email_obj.is_read:
        email_obj.is_read = True
        db.commit()

    return EmailOut(
        id=email_obj.id,
        account_id=email_obj.account_id,
        account_email=account_email,
        gmail_message_id=email_obj.gmail_message_id,
        gmail_thread_id=email_obj.gmail_thread_id,
        message_id_header=email_obj.message_id_header,
        sender=email_obj.sender,
        recipient=email_obj.recipient,
        subject=email_obj.subject,
        html_body=email_obj.html_body,
        received_at=email_obj.received_at,
        fetched_at=email_obj.fetched_at,
        is_read=email_obj.is_read,
        is_starred=email_obj.is_starred,
        folder_status=email_obj.folder_status
    )

@router.patch("/{email_id}", response_model=EmailOut)
def update_email_status(
    email_id: int,
    update_data: EmailUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Update email status (mark read/unread, star/unstar, change folder)."""
    res = db.query(Email, ConnectedAccount.google_email).join(
        ConnectedAccount, Email.account_id == ConnectedAccount.id
    ).filter(Email.id == email_id).first()

    if not res:
        raise HTTPException(status_code=404, detail="Email not found")

    email_obj, account_email = res

    if update_data.is_read is not None:
        email_obj.is_read = update_data.is_read
    if update_data.is_starred is not None:
        email_obj.is_starred = update_data.is_starred
    if update_data.folder_status is not None:
        email_obj.folder_status = update_data.folder_status

    db.commit()
    db.refresh(email_obj)

    return EmailOut(
        id=email_obj.id,
        account_id=email_obj.account_id,
        account_email=account_email,
        gmail_message_id=email_obj.gmail_message_id,
        gmail_thread_id=email_obj.gmail_thread_id,
        message_id_header=email_obj.message_id_header,
        sender=email_obj.sender,
        recipient=email_obj.recipient,
        subject=email_obj.subject,
        html_body=email_obj.html_body,
        received_at=email_obj.received_at,
        fetched_at=email_obj.fetched_at,
        is_read=email_obj.is_read,
        is_starred=email_obj.is_starred,
        folder_status=email_obj.folder_status
    )

@router.post("/{email_id}/reply", response_model=EmailOut)
def reply_to_email(
    email_id: int,
    reply_req: EmailReplyRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Replies to original email using Gmail API users.messages.send.
    Sends FROM the recipient connected account that received the email.
    Includes In-Reply-To and References headers for proper Gmail thread alignment.
    """
    res = db.query(Email, ConnectedAccount).join(
        ConnectedAccount, Email.account_id == ConnectedAccount.id
    ).filter(Email.id == email_id).first()

    if not res:
        raise HTTPException(status_code=404, detail="Email not found")

    email_obj, account = res

    raw_subj = email_obj.subject or ""
    clean_subj = raw_subj if raw_subj.lower().startswith("re:") else f"Re: {raw_subj}"
    to_recipient = email_obj.sender

    msg = MIMEMultipart("alternative")
    msg["From"] = account.google_email
    msg["To"] = to_recipient
    if reply_req.cc:
        msg["Cc"] = reply_req.cc
    if reply_req.bcc:
        msg["Bcc"] = reply_req.bcc

    msg["Subject"] = clean_subj

    orig_msg_id = email_obj.message_id_header or f"<{email_obj.gmail_message_id}@mail.gmail.com>"
    msg["In-Reply-To"] = orig_msg_id
    msg["References"] = orig_msg_id

    msg.attach(MIMEText(reply_req.body_html, "html", "utf-8"))

    sent_result = send_gmail_mime_message(
        db=db,
        account=account,
        raw_mime_bytes=msg.as_bytes(),
        thread_id=email_obj.gmail_thread_id
    )

    sent_gmail_id = sent_result.get("id", f"sent_{int(datetime.datetime.utcnow().timestamp())}")
    sent_thread_id = sent_result.get("threadId", email_obj.gmail_thread_id)

    sent_email_record = Email(
        account_id=account.id,
        gmail_message_id=sent_gmail_id,
        gmail_thread_id=sent_thread_id,
        message_id_header=f"<{sent_gmail_id}@mail.gmail.com>",
        sender=f"Me <{account.google_email}>",
        recipient=to_recipient,
        subject=clean_subj,
        html_body=reply_req.body_html,
        received_at=datetime.datetime.utcnow(),
        fetched_at=datetime.datetime.utcnow(),
        is_read=True,
        is_starred=False,
        folder_status="replied"
    )
    db.add(sent_email_record)
    email_obj.folder_status = "replied"
    db.commit()
    db.refresh(sent_email_record)

    return EmailOut(
        id=sent_email_record.id,
        account_id=sent_email_record.account_id,
        account_email=account.google_email,
        gmail_message_id=sent_email_record.gmail_message_id,
        gmail_thread_id=sent_email_record.gmail_thread_id,
        message_id_header=sent_email_record.message_id_header,
        sender=sent_email_record.sender,
        recipient=sent_email_record.recipient,
        subject=sent_email_record.subject,
        html_body=sent_email_record.html_body,
        received_at=sent_email_record.received_at,
        fetched_at=sent_email_record.fetched_at,
        is_read=sent_email_record.is_read,
        is_starred=sent_email_record.is_starred,
        folder_status=sent_email_record.folder_status
    )

@router.post("/{email_id}/forward", response_model=EmailOut)
def forward_email(
    email_id: int,
    fwd_req: EmailForwardRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Forwards an email with quoted original message formatting via Gmail API users.messages.send.
    """
    res = db.query(Email, ConnectedAccount).join(
        ConnectedAccount, Email.account_id == ConnectedAccount.id
    ).filter(Email.id == email_id).first()

    if not res:
        raise HTTPException(status_code=404, detail="Email not found")

    email_obj, account = res

    raw_subj = email_obj.subject or ""
    clean_subj = raw_subj if raw_subj.lower().startswith("fwd:") else f"Fwd: {raw_subj}"

    fwd_html = f"""{fwd_req.body_html}<br/><br/>
    <div style="border-left: 2px solid #cbd5e1; padding-left: 12px; margin-top: 12px; color: #475569;">
      <div>---------- Forwarded message ---------<br/>
      <strong>From:</strong> {email_obj.sender}<br/>
      <strong>Date:</strong> {email_obj.received_at.strftime('%a, %b %d, %Y at %I:%M %p')}<br/>
      <strong>Subject:</strong> {email_obj.subject}<br/>
      <strong>To:</strong> {email_obj.recipient or account.google_email}<br/>
      </div><br/>
      {email_obj.html_body}
    </div>"""

    msg = MIMEMultipart("alternative")
    msg["From"] = account.google_email
    msg["To"] = fwd_req.to
    if fwd_req.cc:
        msg["Cc"] = fwd_req.cc
    if fwd_req.bcc:
        msg["Bcc"] = fwd_req.bcc

    msg["Subject"] = clean_subj
    msg.attach(MIMEText(fwd_html, "html", "utf-8"))

    sent_result = send_gmail_mime_message(
        db=db,
        account=account,
        raw_mime_bytes=msg.as_bytes()
    )

    sent_gmail_id = sent_result.get("id", f"fwd_{int(datetime.datetime.utcnow().timestamp())}")
    sent_thread_id = sent_result.get("threadId")

    sent_email_record = Email(
        account_id=account.id,
        gmail_message_id=sent_gmail_id,
        gmail_thread_id=sent_thread_id,
        message_id_header=f"<{sent_gmail_id}@mail.gmail.com>",
        sender=f"Me <{account.google_email}>",
        recipient=fwd_req.to,
        subject=clean_subj,
        html_body=fwd_html,
        received_at=datetime.datetime.utcnow(),
        fetched_at=datetime.datetime.utcnow(),
        is_read=True,
        is_starred=False,
        folder_status="inbox"
    )
    db.add(sent_email_record)
    db.commit()
    db.refresh(sent_email_record)

    return EmailOut(
        id=sent_email_record.id,
        account_id=sent_email_record.account_id,
        account_email=account.google_email,
        gmail_message_id=sent_email_record.gmail_message_id,
        gmail_thread_id=sent_email_record.gmail_thread_id,
        message_id_header=sent_email_record.message_id_header,
        sender=sent_email_record.sender,
        recipient=sent_email_record.recipient,
        subject=sent_email_record.subject,
        html_body=sent_email_record.html_body,
        received_at=sent_email_record.received_at,
        fetched_at=sent_email_record.fetched_at,
        is_read=sent_email_record.is_read,
        is_starred=sent_email_record.is_starred,
        folder_status=sent_email_record.folder_status
    )

@router.post("/sync", response_model=SyncResponse)
def trigger_manual_email_sync(
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Manually triggers email sync across all connected accounts immediately."""
    accounts = db.query(ConnectedAccount).all()
    if not accounts:
        return SyncResponse(
            message="No connected Google accounts found. Please click 'Add Account' to connect one.",
            status="idle",
            fetched_emails_count=0
        )

    total_new_emails = 0
    errors = []

    for acc in accounts:
        try:
            new_count = fetch_and_store_emails_for_account(db, acc)
            total_new_emails += new_count
        except Exception as e:
            errors.append(f"{acc.google_email}: {str(e)}")

    if errors:
        return SyncResponse(
            message=f"Sync completed with errors: {'; '.join(errors)}",
            status="partial_error",
            fetched_emails_count=total_new_emails
        )

    return SyncResponse(
        message=f"Successfully synced {len(accounts)} account(s). {total_new_emails} new email(s) fetched.",
        status="success",
        fetched_emails_count=total_new_emails
    )
