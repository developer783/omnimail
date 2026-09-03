import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, field_serializer

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_days: int = 90

class UserOut(BaseModel):
    username: str
    is_authenticated: bool = True

class ConnectedAccountOut(BaseModel):
    id: int
    google_email: str
    connected_at: datetime.datetime
    sync_status: str
    last_synced_at: Optional[datetime.datetime] = None
    error_message: Optional[str] = None
    email_count: int = 0
    unread_count: int = 0

    class Config:
        from_attributes = True

class EmailAttachmentOut(BaseModel):
    id: int
    email_id: int
    filename: str
    mime_type: str
    gmail_attachment_id: str
    size_bytes: int

    class Config:
        from_attributes = True

class EmailOut(BaseModel):
    id: int
    account_id: int
    account_email: str
    gmail_message_id: str
    gmail_thread_id: Optional[str] = None
    message_id_header: Optional[str] = None
    sender: str
    recipient: Optional[str] = None
    subject: str
    html_body: str
    received_at: datetime.datetime
    fetched_at: datetime.datetime
    is_read: bool = False
    is_starred: bool = False
    is_reply: bool = False
    folder_status: str = "inbox"
    attachments: List[EmailAttachmentOut] = []

    @field_serializer("received_at", "fetched_at", mode="plain")
    def serialize_datetime(self, dt: Optional[datetime.datetime]) -> Optional[str]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        iso_str = dt.isoformat()
        if not iso_str.endswith("Z") and not "+" in iso_str:
            iso_str += "Z"
        return iso_str.replace("+00:00", "Z")

    class Config:
        from_attributes = True

class EmailUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    folder_status: Optional[str] = None

class EmailReplyRequest(BaseModel):
    body_html: str
    to: Optional[str] = None
    reply_all: bool = False
    cc: Optional[str] = None
    bcc: Optional[str] = None

class EmailForwardRequest(BaseModel):
    to: str
    body_html: str
    cc: Optional[str] = None
    bcc: Optional[str] = None

class KeywordFilterCreate(BaseModel):
    keyword: str
    field: str = "any" # 'subject', 'sender', 'body', 'any'

class KeywordFilterOut(BaseModel):
    id: int
    keyword: str
    field: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class FolderCounts(BaseModel):
    inbox: int = 0
    unread: int = 0
    starred: int = 0
    follow_up: int = 0
    replied: int = 0
    sent: int = 0
    snoozed: int = 0
    drafts: int = 0

class DraftCreate(BaseModel):
    id: Optional[int] = None
    account_id: int
    gmail_thread_id: Optional[str] = None
    email_id: Optional[int] = None
    to_recipients: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    composer_mode: str = "reply"

class DraftOut(BaseModel):
    id: int
    account_id: int
    account_email: str
    gmail_thread_id: Optional[str] = None
    email_id: Optional[int] = None
    to_recipients: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    composer_mode: str = "reply"
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("created_at", "updated_at", mode="plain")
    def serialize_datetime(self, dt: Optional[datetime.datetime]) -> Optional[str]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        iso_str = dt.isoformat()
        if not iso_str.endswith("Z") and not "+" in iso_str:
            iso_str += "Z"
        return iso_str.replace("+00:00", "Z")

    class Config:
        from_attributes = True

class DraftListResponse(BaseModel):
    items: List[DraftOut]
    total: int

class EmailListResponse(BaseModel):
    items: List[EmailOut]
    total: int
    accounts: List[ConnectedAccountOut]
    folder_counts: FolderCounts
    filters: List[KeywordFilterOut] = []

class SyncResponse(BaseModel):
    message: str
    status: str
    fetched_emails_count: int = 0
