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
    # Render provides postgres:// which SQLAlchemy 2.0 requires as postgresql://
    _raw_db_url: str = os.getenv("DATABASE_URL") or "postgresql://omnimail:omnimail_password@localhost:5432/omnimail"
    
    @property
    def DATABASE_URL(self) -> str:
        url = self._raw_db_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
