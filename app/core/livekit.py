import logging
from livekit import api
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.core.livekit")
settings = get_settings()

# Global client reference to be managed during application lifespan
_livekit_api_client: api.LiveKitAPI | None = None

def get_livekit_client() -> api.LiveKitAPI:
    """
    Returns the global LiveKitAPI client.
    Raises RuntimeError if it has not been initialized.
    """
    global _livekit_api_client
    if _livekit_api_client is None:
        raise RuntimeError("LiveKitAPI client is not initialized. Initialize it in the lifespan.")
    return _livekit_api_client

async def init_livekit_client() -> api.LiveKitAPI:
    """
    Initializes the global LiveKitAPI client.
    """
    global _livekit_api_client
    if _livekit_api_client is None:
        logger.info(f"Initializing LiveKitAPI client pointing to: {settings.livekit_api_url}")
        _livekit_api_client = api.LiveKitAPI(
            url=settings.livekit_api_url,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET
        )
    return _livekit_api_client

async def close_livekit_client():
    """
    Closes the global LiveKitAPI client.
    """
    global _livekit_api_client
    if _livekit_api_client is not None:
        logger.info("Closing LiveKitAPI client")
        await _livekit_api_client.aclose()
        _livekit_api_client = None
