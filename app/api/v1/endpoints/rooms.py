from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.room import RoomCreate, RoomResponse
from app.services.livekit_service import IRoomService
from app.api.dependencies import get_room_service

router = APIRouter()

@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_in: RoomCreate,
    room_service: IRoomService = Depends(get_room_service)
):
    """
    Creates a new LiveKit room.
    """
    try:
        room = await room_service.create_room(room_in)
        return room
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create LiveKit room: {str(e)}"
        )

@router.get("/", response_model=List[RoomResponse])
async def list_rooms(
    room_service: IRoomService = Depends(get_room_service)
):
    """
    Lists all active LiveKit rooms.
    """
    try:
        rooms = await room_service.list_rooms()
        return rooms
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list LiveKit rooms: {str(e)}"
        )

@router.get("/{room_name}", response_model=RoomResponse)
async def get_room(
    room_name: str,
    room_service: IRoomService = Depends(get_room_service)
):
    """
    Retrieves details of an active LiveKit room, including active participants.
    """
    try:
        room = await room_service.get_room(room_name)
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Room '{room_name}' is not currently active"
            )
        return room
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve room details: {str(e)}"
        )

@router.delete("/{room_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_name: str,
    room_service: IRoomService = Depends(get_room_service)
):
    """
    Forcibly closes an active room and disconnects all participants.
    """
    try:
        success = await room_service.delete_room(room_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to close room '{room_name}'"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error closing room: {str(e)}"
        )

@router.delete("/{room_name}/participants/{identity}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_participant(
    room_name: str,
    identity: str,
    room_service: IRoomService = Depends(get_room_service)
):
    """
    Kicks out a specific participant from the active room.
    """
    try:
        success = await room_service.remove_participant(room_name, identity)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to remove participant '{identity}' from room '{room_name}'"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing participant: {str(e)}"
        )
