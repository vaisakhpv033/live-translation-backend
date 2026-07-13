import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.livekit import (
    init_livekit_client, close_livekit_client,
    init_sts_livekit_client, close_sts_livekit_client,
)
from app.core.database import init_db, close_db
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
    Ensures LiveKit API clients and database are gracefully created and cleaned up.
    """
    logger.info("Initializing Translation LiveKit API Client...")
    await init_livekit_client()

    logger.info("Initializing STS LiveKit API Client...")
    await init_sts_livekit_client()

    logger.info("Initializing PostgreSQL database...")
    await init_db(settings.DATABASE_URL)

    # Self-healing database sweep for ongoing reports
    import asyncio
    from app.services.background_evaluation import sweep_and_recover_reports
    asyncio.create_task(sweep_and_recover_reports())

    yield

    logger.info("Closing Translation LiveKit API Client...")
    await close_livekit_client()

    logger.info("Closing STS LiveKit API Client...")
    await close_sts_livekit_client()

    logger.info("Closing database connections...")
    await close_db()

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
