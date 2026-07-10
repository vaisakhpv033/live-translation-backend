from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.token import TokenRequest, TokenResponse
from app.services.livekit_service import IRoomService
from app.api.dependencies import get_room_service

router = APIRouter()

@router.post("/{room_name}/tokens", response_model=TokenResponse)
async def generate_token(
    room_name: str,
    token_req: TokenRequest,
    room_service: IRoomService = Depends(get_room_service)
):
    """
    Generates a LiveKit JWT connection token for a participant to join a specified room.
    The generated token restricts publishing capabilities to audio-only (microphone).
    Injects spoken language and target language as participant attributes.
    """
    try:
        # Check if the room exists on the server first
        room_info = await room_service.get_room(room_name)
        if not room_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Room '{room_name}' not found. Please ensure the host has started the room first."
            )

        token_response = room_service.generate_token(room_name, token_req)
        return token_response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate access token: {str(e)}"
        )
