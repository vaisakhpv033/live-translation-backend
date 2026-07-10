import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from livekit import api
from app.schemas.room import RoomCreate, RoomResponse, ParticipantInfo
from app.schemas.token import TokenRequest, TokenResponse
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.services.livekit_service")
settings = get_settings()

class IRoomService(ABC):
    """
    Interface definition for LiveKit Room and Participant operations (Interface Segregation).
    """
    @abstractmethod
    async def create_room(self, room_in: RoomCreate) -> RoomResponse:
        """Creates a new LiveKit room."""
        pass

    @abstractmethod
    async def list_rooms(self) -> List[RoomResponse]:
        """Lists active LiveKit rooms."""
        pass

    @abstractmethod
    async def get_room(self, room_name: str) -> Optional[RoomResponse]:
        """Gets details of an active LiveKit room including active participants."""
        pass

    @abstractmethod
    async def delete_room(self, room_name: str) -> bool:
        """Deletes/closes a LiveKit room."""
        pass

    @abstractmethod
    async def remove_participant(self, room_name: str, identity: str) -> bool:
        """Removes a participant from a LiveKit room."""
        pass

    @abstractmethod
    def generate_token(self, room_name: str, token_req: TokenRequest) -> TokenResponse:
        """Generates a joining access token for a participant."""
        pass


class LiveKitRoomService(IRoomService):
    """
    Implementation of IRoomService using LiveKitAPI client (Dependency Inversion).
    """
    def __init__(self, lk_client: api.LiveKitAPI):
        self.client = lk_client

    async def create_room(self, room_in: RoomCreate) -> RoomResponse:
        logger.info(f"Creating room: {room_in.name}")
        request = api.CreateRoomRequest(
            name=room_in.name,
            empty_timeout=room_in.empty_timeout,
            max_participants=room_in.max_participants,
            metadata=room_in.metadata
        )
        room_info = await self.client.room.create_room(request)

        # Dispatch the analysis-agent and translation-agent explicitly to this room
        for agent_name in ["translation-agent", "analysis-agent"]:
            try:
                existing_dispatches = await self.client.agent_dispatch.list_dispatch(
                    room_name=room_in.name
                )
                already_dispatched = any(
                    d.agent_name == agent_name for d in existing_dispatches
                )

                if not already_dispatched:
                    logger.info(f"Triggering explicit agent dispatch for {agent_name} in room {room_in.name}")
                    dispatch_request = api.CreateAgentDispatchRequest(
                        agent_name=agent_name,
                        room=room_in.name
                    )
                    await self.client.agent_dispatch.create_dispatch(dispatch_request)
                    logger.info(f"Successfully dispatched {agent_name} to room {room_in.name}")
                else:
                    logger.info(f"{agent_name} already dispatched in room {room_in.name}, skipping")
            except Exception as e:
                logger.warning(f"Failed to create explicit agent dispatch for {agent_name} in room {room_in.name}: {e}")

        return RoomResponse(
            name=room_info.name,
            sid=room_info.sid,
            empty_timeout=room_info.empty_timeout,
            max_participants=room_info.max_participants,
            num_participants=room_info.num_participants,
            metadata=room_info.metadata,
            active_participants=[]
        )

    async def list_rooms(self) -> List[RoomResponse]:
        logger.info("Listing active rooms")
        request = api.ListRoomsRequest()
        response = await self.client.room.list_rooms(request)
        
        rooms = []
        for room_info in response.rooms:
            rooms.append(
                RoomResponse(
                    name=room_info.name,
                    sid=room_info.sid,
                    empty_timeout=room_info.empty_timeout,
                    max_participants=room_info.max_participants,
                    num_participants=room_info.num_participants,
                    metadata=room_info.metadata,
                    active_participants=[]
                )
            )
        return rooms

    async def get_room(self, room_name: str) -> Optional[RoomResponse]:
        logger.info(f"Getting room details for: {room_name}")
        # List rooms filtered by name
        list_request = api.ListRoomsRequest(names=[room_name])
        list_response = await self.client.room.list_rooms(list_request)
        
        if not list_response.rooms:
            logger.warning(f"Room {room_name} not found")
            return None
            
        room_info = list_response.rooms[0]
        
        # Fetch participants in this room
        part_request = api.ListParticipantsRequest(room=room_name)
        part_response = await self.client.room.list_participants(part_request)
        
        active_participants = []
        for p in part_response.participants:
            # Safely extract attributes dict if present
            attrs = {}
            if hasattr(p, "attributes"):
                attrs = dict(p.attributes)
            elif hasattr(p, "metadata") and p.metadata:
                # Fallback attributes representation if needed
                pass
                
            active_participants.append(
                ParticipantInfo(
                    identity=p.identity,
                    name=p.name,
                    state=str(p.state),
                    joined_at=p.joined_at,
                    metadata=p.metadata,
                    attributes=attrs
                )
            )
            
        return RoomResponse(
            name=room_info.name,
            sid=room_info.sid,
            empty_timeout=room_info.empty_timeout,
            max_participants=room_info.max_participants,
            num_participants=room_info.num_participants,
            metadata=room_info.metadata,
            active_participants=active_participants
        )

    async def delete_room(self, room_name: str) -> bool:
        logger.info(f"Deleting room: {room_name}")
        try:
            request = api.DeleteRoomRequest(room=room_name)
            await self.client.room.delete_room(request)
            return True
        except Exception as e:
            logger.error(f"Error deleting room {room_name}: {str(e)}")
            return False

    async def remove_participant(self, room_name: str, identity: str) -> bool:
        logger.info(f"Removing participant {identity} from room {room_name}")
        try:
            request = api.RemoveParticipantRequest(room=room_name, identity=identity)
            await self.client.room.remove_participant(request)
            return True
        except Exception as e:
            logger.error(f"Error removing participant {identity}: {str(e)}")
            return False

    def generate_token(self, room_name: str, token_req: TokenRequest) -> TokenResponse:
        logger.info(f"Generating token for {token_req.identity} in room {room_name}")
        
        # Audio-only connection grants:
        # Publish microphone (microphone source), subscribe to other audio, join room.
        # Enforcing only microphone source restrict publishes camera/screen share.
        grants = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_sources=["microphone"]
        )
        
        # Create token
        token = (
            api.AccessToken(
                api_key=settings.LIVEKIT_API_KEY,
                api_secret=settings.LIVEKIT_API_SECRET
            )
            .with_identity(token_req.identity)
            .with_grants(grants)
        )
        
        # Set user display name if provided
        if token_req.username:
            token.with_name(token_req.username)
            
        attributes = {
            "speaking_language": token_req.speaking_language,
            "language": token_req.speaking_language,  # compatibility fallback
        }
        if token_req.target_language:
            attributes["target_language"] = token_req.target_language
        
        if token_req.username:
            attributes["username"] = token_req.username

        token.with_attributes(attributes)
        
        # Also store language details in metadata as a fallback for some clients
        metadata_dict = {
            "language": token_req.speaking_language,
            "speaking_language": token_req.speaking_language,
        }
        if token_req.target_language:
            metadata_dict["target_language"] = token_req.target_language
            
        import json
        token.with_metadata(json.dumps(metadata_dict))
        
        jwt_token = token.to_jwt()
        
        return TokenResponse(
            token=jwt_token,
            room_name=room_name,
            identity=token_req.identity
        )
