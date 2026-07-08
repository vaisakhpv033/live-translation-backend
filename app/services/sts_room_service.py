import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional
from livekit import api
from app.schemas.sts_room import STSRoomCreate, STSRoomResponse, STSTokenRequest
from app.schemas.room import RoomResponse, ParticipantInfo
from app.schemas.token import TokenResponse
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.services.sts_room_service")
settings = get_settings()

# Persona name mapping — matches the customer-agent-sts persona presets
PERSONA_NAMES = {
    "default": "RahulNair",
    "angry": "RajeshKumar",
    "rude": "VikramSingh",
    "cool": "RohanVerma",
    "skeptical": "SureshGupta",
    "confused": "SunitaSharma",
    "demanding": "AnanyaSen",
    "wtw": "SarahMitchell",
}


def _generate_room_name(persona: str, customer_name: Optional[str] = None) -> str:
    """
    Generates a unique room name in the format: MF-{CustomerName}-{uuid_short}.
    Customer name is resolved from the persona preset if not provided.
    """
    prefix = customer_name or PERSONA_NAMES.get(persona.lower(), "Customer")
    prefix = prefix.replace(" ", "")
    short_id = uuid.uuid4().hex[:8]
    return f"MF-{prefix}-{short_id}"


class ISTSRoomService(ABC):
    """
    Interface for STS Room operations (Interface Segregation).
    """
    @abstractmethod
    async def create_room(self, room_in: STSRoomCreate) -> STSRoomResponse:
        """Creates a new STS room with auto-generated name and pre-generated token."""
        pass

    @abstractmethod
    async def list_rooms(self) -> List[RoomResponse]:
        """Lists active STS rooms."""
        pass

    @abstractmethod
    async def get_room(self, room_name: str) -> Optional[RoomResponse]:
        """Gets details of an active STS room including active participants."""
        pass

    @abstractmethod
    async def delete_room(self, room_name: str) -> bool:
        """Deletes/closes an STS room."""
        pass

    @abstractmethod
    def generate_token(self, room_name: str, token_req: STSTokenRequest) -> TokenResponse:
        """Generates a join token for an STS room."""
        pass


class LiveKitSTSRoomService(ISTSRoomService):
    """
    Implementation of ISTSRoomService using the STS LiveKitAPI client (Dependency Inversion).
    """
    def __init__(self, lk_client: api.LiveKitAPI):
        self.client = lk_client

    async def create_room(self, room_in: STSRoomCreate) -> STSRoomResponse:
        # Generate unique room name
        room_name = _generate_room_name(room_in.persona, room_in.customer_name)
        logger.info(f"Creating STS room: {room_name} (persona={room_in.persona})")

        # Build metadata JSON that the STS agent reads from ctx.job.metadata
        metadata = {
            "persona": room_in.persona,
            "language": room_in.language,
        }
        if room_in.custom_instructions:
            metadata["custom_instructions"] = room_in.custom_instructions
        if room_in.customer_name:
            metadata["name"] = room_in.customer_name

        # Forward optional persona overrides
        for field in ["age", "occupation", "location", "monthly_income", "current_savings", "risk_appetite"]:
            value = getattr(room_in, field, None)
            if value is not None:
                metadata[field] = value

        metadata_json = json.dumps(metadata)

        # Create the room on the STS LiveKit server
        create_request = api.CreateRoomRequest(
            name=room_name,
            empty_timeout=room_in.empty_timeout,
            max_participants=room_in.max_participants,
            metadata=metadata_json,
        )
        room_info = await self.client.room.create_room(create_request)

        # Explicitly dispatch the Customer-sts agent to the room
        try:
            logger.info(f"Triggering explicit agent dispatch for Customer-sts in room {room_name}")
            dispatch_request = api.CreateAgentDispatchRequest(
                agent_name="Customer-sts",
                room=room_name,
                metadata=metadata_json,
            )
            await self.client.agent_dispatch.create_dispatch(dispatch_request)
            logger.info(f"Successfully dispatched Customer-sts agent to room {room_name}")
        except Exception as e:
            logger.warning(
                f"Failed to create explicit agent dispatch: {e}. "
                "Ensure your agent worker is running and registered, or that automatic dispatch rules are configured."
            )

        # Pre-generate a join token for the human participant
        identity = f"user-{uuid.uuid4().hex[:6]}"
        token = self._build_token(room_name, identity, room_in.customer_name)

        return STSRoomResponse(
            name=room_info.name,
            sid=room_info.sid,
            empty_timeout=room_info.empty_timeout,
            max_participants=room_info.max_participants,
            num_participants=room_info.num_participants,
            metadata=room_info.metadata,
            livekit_url=settings.STS_LIVEKIT_URL,
            token=token,
            identity=identity,
        )

    async def list_rooms(self) -> List[RoomResponse]:
        logger.info("Listing active STS rooms")
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
                    active_participants=[],
                )
            )
        return rooms

    async def get_room(self, room_name: str) -> Optional[RoomResponse]:
        logger.info(f"Getting STS room details for: {room_name}")
        list_request = api.ListRoomsRequest(names=[room_name])
        list_response = await self.client.room.list_rooms(list_request)

        if not list_response.rooms:
            logger.warning(f"STS room {room_name} not found")
            return None

        room_info = list_response.rooms[0]

        # Fetch participants
        part_request = api.ListParticipantsRequest(room=room_name)
        part_response = await self.client.room.list_participants(part_request)

        active_participants = []
        for p in part_response.participants:
            attrs = {}
            if hasattr(p, "attributes"):
                attrs = dict(p.attributes)

            active_participants.append(
                ParticipantInfo(
                    identity=p.identity,
                    name=p.name,
                    state=str(p.state),
                    joined_at=p.joined_at,
                    metadata=p.metadata,
                    attributes=attrs,
                )
            )

        return RoomResponse(
            name=room_info.name,
            sid=room_info.sid,
            empty_timeout=room_info.empty_timeout,
            max_participants=room_info.max_participants,
            num_participants=room_info.num_participants,
            metadata=room_info.metadata,
            active_participants=active_participants,
        )

    async def delete_room(self, room_name: str) -> bool:
        logger.info(f"Deleting STS room: {room_name}")
        try:
            request = api.DeleteRoomRequest(room=room_name)
            await self.client.room.delete_room(request)
            return True
        except Exception as e:
            logger.error(f"Error deleting STS room {room_name}: {str(e)}")
            return False

    def generate_token(self, room_name: str, token_req: STSTokenRequest) -> TokenResponse:
        logger.info(f"Generating STS token for {token_req.identity} in room {room_name}")
        jwt_token = self._build_token(room_name, token_req.identity, token_req.username)
        return TokenResponse(
            token=jwt_token,
            room_name=room_name,
            identity=token_req.identity,
        )

    def _build_token(self, room_name: str, identity: str, username: Optional[str] = None) -> str:
        """
        Builds a LiveKit JWT token using the STS LiveKit credentials.
        Grants audio-only publishing (microphone) and full subscribe access.
        """
        grants = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_sources=["microphone"],
        )

        token = (
            api.AccessToken(
                api_key=settings.STS_LIVEKIT_API_KEY,
                api_secret=settings.STS_LIVEKIT_API_SECRET,
            )
            .with_identity(identity)
            .with_grants(grants)
        )

        if username:
            token.with_name(username)

        return token.to_jwt()
