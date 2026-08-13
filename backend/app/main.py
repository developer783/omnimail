import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import auth, google_oauth, emails, filters
from app.scheduler import start_scheduler, stop_scheduler

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

# Automatically create database tables on startup
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info(f"Starting {settings.APP_NAME} in environment: {settings.ENV}")
    start_scheduler()
    yield
    # Shutdown actions
    logger.info("Shutting down application...")
    stop_scheduler()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Multi-User Email Aggregation API with Google OAuth 2.0 Gmail Integration",
    lifespan=lifespan
)

# Configure CORS for frontend access
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    settings.FRONTEND_URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(google_oauth.router)
app.include_router(emails.router)
app.include_router(filters.router)

@app.get("/", tags=["Root"])
def root():
    return {
        "status": "online",
        "message": "Omnimail FastAPI Backend Server is running successfully!",
        "documentation": "/docs",
        "health_check": "/health"
    }

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENV
    }
