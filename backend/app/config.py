import os
import base64
from pydantic_settings import BaseSettings
from cryptography.fernet import Fernet

class Settings(BaseSettings):
    APP_NAME: str = "Email Aggregator API"
    ENV: str = os.getenv("ENV", "development")
    
    # Auth configuration
    SHARED_USERNAME: str = os.getenv("SHARED_USERNAME", "admin")
    SHARED_PASSWORD: str = os.getenv("SHARED_PASSWORD", "admin123")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-long-lived-jwt-key-30-days-expiry-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 90 # 90-day persistent long-lived session

    # Token Encryption Key for stored OAuth credentials
    TOKEN_ENCRYPTION_KEY: str = os.getenv("TOKEN_ENCRYPTION_KEY") or Fernet.generate_key().decode()

    # Database configuration
    # Render provides postgres:// (or a URL with an explicit driver); normalize every Postgres
    # URL to the psycopg (v3) driver, which is the one installed via requirements.txt.
    _raw_db_url: str = os.getenv("DATABASE_URL") or "postgresql://omnimail:omnimail_password@localhost:5432/omnimail"

    @property
    def DATABASE_URL(self) -> str:
        url = self._raw_db_url
        for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://", "postgresql+psycopg://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Memory / storage limits (sized for a 512 MB instance and a small Postgres database)
    # Sent/replied messages are kept past the 24h inbound window only as thread context for this long.
    OUTBOUND_RETENTION_DAYS: int = int(os.getenv("OUTBOUND_RETENTION_DAYS", "7"))
    # Messages fetched per account per sync, and how many are committed to the DB at a time.
    SYNC_MAX_RESULTS: int = int(os.getenv("SYNC_MAX_RESULTS", "50"))
    SYNC_COMMIT_BATCH: int = int(os.getenv("SYNC_COMMIT_BATCH", "10"))
    # How often all accounts are synced, and how many accounts are synced at the same time.
    SYNC_INTERVAL_MINUTES: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "2"))
    SYNC_CONCURRENCY: int = int(os.getenv("SYNC_CONCURRENCY", "4"))
    # Bodies above this size get their embedded data: URIs stripped before being stored.
    MAX_STORED_BODY_BYTES: int = int(os.getenv("MAX_STORED_BODY_BYTES", str(1024 * 1024)))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
