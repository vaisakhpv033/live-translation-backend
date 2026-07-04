from fastapi import Depends
from livekit import api
from app.core.livekit import get_livekit_client
from app.services.livekit_service import IRoomService, LiveKitRoomService

def get_livekit_api_client() -> api.LiveKitAPI:
    """
    FastAPI dependency that returns the active LiveKitAPI client.
    """
    return get_livekit_client()

def get_room_service(
    lk_client: api.LiveKitAPI = Depends(get_livekit_api_client)
) -> IRoomService:
    """
    FastAPI dependency that returns an instance of IRoomService.
    Ensures dependency inversion by returning the interface abstraction.
    """
    return LiveKitRoomService(lk_client)
