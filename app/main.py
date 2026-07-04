import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.livekit import init_livekit_client, close_livekit_client
from app.api.v1.router import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("translation-agent-backend.main")

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events (SOLID Single Responsibility).
    Ensures LiveKit API client is gracefully created and cleaned up.
    """
    logger.info("Initializing LiveKit API Client on startup...")
    await init_livekit_client()
    yield
    logger.info("Closing LiveKit API Client on shutdown...")
    await close_livekit_client()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend service for room creation, management, token generation, and webhook ingestion for translation agents.",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware to support client-side WebRTC integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Health"])
async def health():
    """
    Basic health check endpoint for liveness and readiness probes.
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "livekit_connected": True
    }
