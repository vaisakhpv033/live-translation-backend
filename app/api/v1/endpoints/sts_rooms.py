from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.sts_room import STSRoomCreate, STSRoomResponse, STSTokenRequest
from app.schemas.room import RoomResponse
from app.schemas.token import TokenResponse
from app.services.sts_room_service import ISTSRoomService
from app.api.dependencies import get_sts_room_service

router = APIRouter()


@router.post("/", response_model=STSRoomResponse, status_code=status.HTTP_201_CREATED)
async def create_sts_room(
    room_in: STSRoomCreate,
    room_service: ISTSRoomService = Depends(get_sts_room_service)
):
    """
    Creates a new STS agent room with an auto-generated unique name.
    The room name follows the pattern MF-{CustomerName}-{uuid_short}.
    Returns the room details, LiveKit URL, and a pre-generated join token.
    """
    try:
        room = await room_service.create_room(room_in)
        return room
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create STS room: {str(e)}"
        )


@router.get("/", response_model=List[RoomResponse])
async def list_sts_rooms(
    room_service: ISTSRoomService = Depends(get_sts_room_service)
):
    """
    Lists all active STS rooms on the STS LiveKit server.
    """
    try:
        rooms = await room_service.list_rooms()
        return rooms
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list STS rooms: {str(e)}"
        )


@router.get("/{room_name}", response_model=RoomResponse)
async def get_sts_room(
    room_name: str,
    room_service: ISTSRoomService = Depends(get_sts_room_service)
):
    """
    Retrieves details of an active STS room, including active participants.
    """
    try:
        room = await room_service.get_room(room_name)
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"STS room '{room_name}' is not currently active"
            )
        return room
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve STS room details: {str(e)}"
        )


@router.delete("/{room_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sts_room(
    room_name: str,
    room_service: ISTSRoomService = Depends(get_sts_room_service)
):
    """
    Forcibly closes an active STS room and disconnects all participants.
    """
    try:
        success = await room_service.delete_room(room_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to close STS room '{room_name}'"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error closing STS room: {str(e)}"
        )


@router.post("/{room_name}/tokens", response_model=TokenResponse)
async def generate_sts_token(
    room_name: str,
    token_req: STSTokenRequest,
    room_service: ISTSRoomService = Depends(get_sts_room_service)
):
    """
    Generates a LiveKit JWT connection token for a participant to join a specified STS room.
    """
    try:
        token_response = room_service.generate_token(room_name, token_req)
        return token_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate STS access token: {str(e)}"
        )
