import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import engine, Base
from app.routers.auth import router as auth_router
from app.routers.google_oauth import router as google_oauth_router
from app.routers.emails import router as emails_router
from app.routers.filters import router as filters_router
from app.scheduler import start_scheduler, stop_scheduler

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

# Automatically create database tables on startup with logging verification
logger.info(f"Connecting to database host: {engine.url.host or 'local'} (database: {engine.url.database})...")
Base.metadata.create_all(bind=engine)
logger.info("Successfully connected to PostgreSQL database and verified all database tables!")

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
app.include_router(auth_router)
app.include_router(google_oauth_router)
app.include_router(emails_router)
app.include_router(filters_router)

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENV
    }

# Check for compiled frontend build directory
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
assets_dir = os.path.join(frontend_dist, "assets")

if os.path.exists(frontend_dist) and os.path.exists(assets_dir):
    logger.info(f"Mounting static frontend build from {frontend_dist}")
    app.mount("/assets", StaticFiles(directory=assets_dir), name="static_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Allow API endpoints like /health, /docs, /openapi.json to bypass SPA handler
        if full_path in ["health", "docs", "openapi.json", "redoc"]:
            return None
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    @app.get("/", tags=["Root"])
    def root():
        return {
            "status": "online",
            "message": "Omnimail FastAPI Backend Server is running successfully!",
            "documentation": "/docs",
            "health_check": "/health"
        }
