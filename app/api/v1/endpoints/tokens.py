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
        # Check if the room exists or is active (optional, depending on flow)
        # For ease of join flow, we can let them generate a token even if room is not yet started,
        # since joining a non-existent room in LiveKit will auto-create it if allowed.
        token_response = room_service.generate_token(room_name, token_req)
        return token_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate access token: {str(e)}"
        )
