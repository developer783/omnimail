import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import ConnectedAccount, Email, Draft
from app.schemas import (
    DraftCreate, DraftOut, DraftListResponse, EmailOut
)
from app.security import verify_jwt_token
from app.gmail_service import send_gmail_mime_message

router = APIRouter(prefix="/drafts", tags=["Drafts"])

@router.get("", response_model=DraftListResponse)
def get_drafts(
    account_id: Optional[int] = Query(None, description="Filter by connected account ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Returns list of active drafts, optionally filtered by account_id."""
    query = db.query(Draft, ConnectedAccount.google_email).join(
        ConnectedAccount, Draft.account_id == ConnectedAccount.id
    )

    if account_id:
        query = query.filter(Draft.account_id == account_id)

    results = query.order_by(desc(Draft.updated_at)).all()

    items = []
    for draft_obj, account_email in results:
        items.append(
            DraftOut(
                id=draft_obj.id,
                account_id=draft_obj.account_id,
                account_email=account_email,
                gmail_thread_id=draft_obj.gmail_thread_id,
                email_id=draft_obj.email_id,
                to_recipients=draft_obj.to_recipients,
                cc=draft_obj.cc,
                bcc=draft_obj.bcc,
                subject=draft_obj.subject or "",
                html_body=draft_obj.html_body or "",
                composer_mode=draft_obj.composer_mode,
                created_at=draft_obj.created_at,
                updated_at=draft_obj.updated_at
            )
        )

    return DraftListResponse(items=items, total=len(items))

@router.get("/{draft_id}", response_model=DraftOut)
def get_draft_by_id(
    draft_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Fetch single draft record."""
    res = db.query(Draft, ConnectedAccount.google_email).join(
        ConnectedAccount, Draft.account_id == ConnectedAccount.id
    ).filter(Draft.id == draft_id).first()

    if not res:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft_obj, account_email = res
    return DraftOut(
        id=draft_obj.id,
        account_id=draft_obj.account_id,
        account_email=account_email,
        gmail_thread_id=draft_obj.gmail_thread_id,
        email_id=draft_obj.email_id,
        to_recipients=draft_obj.to_recipients,
        cc=draft_obj.cc,
        bcc=draft_obj.bcc,
        subject=draft_obj.subject or "",
        html_body=draft_obj.html_body or "",
        composer_mode=draft_obj.composer_mode,
        created_at=draft_obj.created_at,
        updated_at=draft_obj.updated_at
    )

@router.post("", response_model=DraftOut)
def save_or_update_draft(
    draft_req: DraftCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Creates or updates a draft record (autosave endpoint)."""
    account = db.query(ConnectedAccount).filter(ConnectedAccount.id == draft_req.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Connected account not found")

    draft_obj = None

    if draft_req.id:
        draft_obj = db.query(Draft).filter(Draft.id == draft_req.id).first()

    if not draft_obj and draft_req.email_id and draft_req.email_id > 0:
        draft_obj = db.query(Draft).filter(
            Draft.account_id == draft_req.account_id,
            Draft.email_id == draft_req.email_id
        ).first()

    now_utc = datetime.datetime.now(datetime.timezone.utc)

    if draft_obj:
        draft_obj.to_recipients = draft_req.to_recipients
        draft_obj.cc = draft_req.cc
        draft_obj.bcc = draft_req.bcc
        draft_obj.subject = draft_req.subject
        draft_obj.html_body = draft_req.html_body
        draft_obj.composer_mode = draft_req.composer_mode
        draft_obj.gmail_thread_id = draft_req.gmail_thread_id or draft_obj.gmail_thread_id
        draft_obj.updated_at = now_utc
    else:
        draft_obj = Draft(
            account_id=draft_req.account_id,
            gmail_thread_id=draft_req.gmail_thread_id,
            email_id=draft_req.email_id if (draft_req.email_id and draft_req.email_id > 0) else None,
            to_recipients=draft_req.to_recipients,
            cc=draft_req.cc,
            bcc=draft_req.bcc,
            subject=draft_req.subject,
            html_body=draft_req.html_body,
            composer_mode=draft_req.composer_mode,
            created_at=now_utc,
            updated_at=now_utc
        )
        db.add(draft_obj)

    db.commit()
    db.refresh(draft_obj)

    return DraftOut(
        id=draft_obj.id,
        account_id=draft_obj.account_id,
        account_email=account.google_email,
        gmail_thread_id=draft_obj.gmail_thread_id,
        email_id=draft_obj.email_id,
        to_recipients=draft_obj.to_recipients,
        cc=draft_obj.cc,
        bcc=draft_obj.bcc,
        subject=draft_obj.subject or "",
        html_body=draft_obj.html_body or "",
        composer_mode=draft_obj.composer_mode,
        created_at=draft_obj.created_at,
        updated_at=draft_obj.updated_at
    )

@router.delete("/{draft_id}")
def delete_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Deletes a draft record when user discards it."""
    draft_obj = db.query(Draft).filter(Draft.id == draft_id).first()
    if not draft_obj:
        raise HTTPException(status_code=404, detail="Draft not found")

    db.delete(draft_obj)
    db.commit()
    return {"message": "Draft deleted successfully"}

@router.post("/{draft_id}/send", response_model=EmailOut)
def send_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_jwt_token)
):
    """Sends draft via Gmail API, creates sent Email record, and deletes draft row."""
    res = db.query(Draft, ConnectedAccount).join(
        ConnectedAccount, Draft.account_id == ConnectedAccount.id
    ).filter(Draft.id == draft_id).first()

    if not res:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft_obj, account = res

    if not draft_obj.to_recipients or not draft_obj.to_recipients.strip():
        raise HTTPException(status_code=400, detail="Cannot send draft without a recipient email address.")

    clean_subj = draft_obj.subject or "No Subject"
    body_html = draft_obj.html_body or ""

    msg = MIMEMultipart("alternative")
    msg["From"] = account.google_email
    msg["To"] = draft_obj.to_recipients
    if draft_obj.cc:
        msg["Cc"] = draft_obj.cc
    if draft_obj.bcc:
        msg["Bcc"] = draft_obj.bcc

    msg["Subject"] = clean_subj

    # If linked to original email, set threading headers
    orig_email = None
    if draft_obj.email_id:
        orig_email = db.query(Email).filter(Email.id == draft_obj.email_id).first()

    if orig_email:
        orig_msg_id = orig_email.message_id_header or f"<{orig_email.gmail_message_id}@mail.gmail.com>"
        msg["In-Reply-To"] = orig_msg_id
        msg["References"] = orig_msg_id

    msg.attach(MIMEText(body_html, "html", "utf-8"))

    sent_result = send_gmail_mime_message(
        db=db,
        account=account,
        raw_mime_bytes=msg.as_bytes(),
        thread_id=draft_obj.gmail_thread_id
    )

    sent_gmail_id = sent_result.get("id", f"sent_{int(datetime.datetime.utcnow().timestamp())}")
    target_thread_id = (draft_obj.gmail_thread_id or
                        (orig_email.gmail_thread_id if orig_email else None) or
                        sent_result.get("threadId") or
                        sent_gmail_id)

    if orig_email and (not orig_email.gmail_thread_id or orig_email.gmail_thread_id != target_thread_id):
        orig_email.gmail_thread_id = target_thread_id

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    is_true_reply = bool(orig_email) or bool(draft_obj.composer_mode in ["reply", "reply_all"] and target_thread_id)

    sent_email_record = Email(
        account_id=account.id,
        gmail_message_id=sent_gmail_id,
        gmail_thread_id=target_thread_id,
        message_id_header=f"<{sent_gmail_id}@mail.gmail.com>",
        sender=f"Me <{account.google_email}>",
        recipient=draft_obj.to_recipients,
        subject=clean_subj,
        html_body=body_html,
        received_at=now_utc,
        fetched_at=now_utc,
        is_read=True,
        is_starred=False,
        is_reply=is_true_reply,
        folder_status="replied" if is_true_reply else "sent"
    )
    if orig_email and is_true_reply:
        orig_email.folder_status = "replied"

    db.add(sent_email_record)

    # Delete draft row
    db.delete(draft_obj)
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
        is_reply=sent_email_record.is_reply,
        folder_status=sent_email_record.folder_status,
        attachments=[]
    )
