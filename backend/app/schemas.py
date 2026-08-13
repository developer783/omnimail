import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel

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
    folder_status: str = "inbox"

    class Config:
        from_attributes = True

class EmailUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    folder_status: Optional[str] = None

class EmailReplyRequest(BaseModel):
    body_html: str
    reply_all: bool = False
    cc: Optional[str] = None
    bcc: Optional[str] = None

class EmailForwardRequest(BaseModel):
    to: str
    body_html: str
    cc: Optional[str] = None
    bcc: Optional[str] = None

class FolderCounts(BaseModel):
    inbox: int = 0
    unread: int = 0
    starred: int = 0
    follow_up: int = 0
    replied: int = 0
    snoozed: int = 0

class EmailListResponse(BaseModel):
    items: List[EmailOut]
    total: int
    accounts: List[ConnectedAccountOut]
    folder_counts: FolderCounts

class SyncResponse(BaseModel):
    message: str
    status: str
    fetched_emails_count: int = 0
