import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"

    id = Column(Integer, primary_key=True, index=True)
    google_email = Column(String(255), nullable=False, unique=True, index=True)
    access_token = Column(Text, nullable=False)   # Encrypted Fernet string
    refresh_token = Column(Text, nullable=False)  # Encrypted Fernet string
    token_expiry = Column(DateTime, nullable=True)
    connected_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    sync_status = Column(String(50), default="idle", nullable=False) # 'idle', 'syncing', 'success', 'error'
    last_synced_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    emails = relationship("Email", back_populates="account", cascade="all, delete-orphan")

class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("connected_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    gmail_message_id = Column(String(255), nullable=False, index=True)
    gmail_thread_id = Column(String(255), nullable=True, index=True)
    message_id_header = Column(String(512), nullable=True)
    sender = Column(String(512), nullable=False, default="Unknown Sender")
    recipient = Column(String(512), nullable=True)
    subject = Column(String(1024), nullable=False, default="No Subject")
    html_body = Column(Text, nullable=False)
    received_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    is_starred = Column(Boolean, default=False, nullable=False, index=True)
    folder_status = Column(String(50), default="inbox", nullable=False, index=True) # 'inbox', 'follow_up', 'replied', 'snoozed'

    __table_args__ = (
        UniqueConstraint("account_id", "gmail_message_id", name="uq_account_gmail_msg"),
    )

    account = relationship("ConnectedAccount", back_populates="emails")

class KeywordFilter(Base):
    __tablename__ = "keyword_filters"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(255), nullable=False)
    field = Column(String(50), nullable=False, default="any") # 'subject', 'sender', 'body', 'any'
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
