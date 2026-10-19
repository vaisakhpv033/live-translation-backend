import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional
from fastapi import HTTPException, status
from livekit import api

from app.schemas.autocoach import (
    AutoCoachSessionCreate,
    AutoCoachSessionResponse,
    AutoCoachTokenRequest,
)
from app.schemas.room import RoomResponse, ParticipantInfo
from app.schemas.token import TokenResponse
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.services.autocoach_service")
settings = get_settings()

# Default patient names based on persona & language presets
DEFAULT_PATIENT_NAMES = {
    "en-US": {
        "default": "Mukul Sharma",
        "skeptical": "David Miller",
        "angry": "Robert Jenkins",
        "confused": "Eleanor Vance",
        "demanding": "Victoria Sterling",
        "anxious": "James Callahan",
    },
    "es-US": {
        "default": "Carlos Rodriguez",
        "skeptical": "Mateo Hernandez",
        "angry": "Hector Ramirez",
        "confused": "Sofia Morales",
        "demanding": "Valentina Cruz",
        "anxious": "Alejandro Gomez",
    },
    "code-mixed": {
        "default": "Maria Gonzalez",
        "skeptical": "Lucas Fernandez",
        "angry": "Javier Castillo",
        "confused": "Camila Reyes",
        "demanding": "Elena Ortiz",
        "anxious": "Diego Alvarez",
    },
}


def _resolve_patient_name(language: str, persona: str, requested_name: Optional[str]) -> str:
    """Resolves a realistic patient name given the language and persona archetype."""
    if requested_name and requested_name.strip():
        return requested_name.strip()
    
    lang_key = "en-US"
    clean_lang = language.lower()
    if "es" in clean_lang and "en" not in clean_lang:
        lang_key = "es-US"
    elif "code" in clean_lang or "spanglish" in clean_lang or ("es" in clean_lang and "en" in clean_lang):
        lang_key = "code-mixed"

    persona_map = DEFAULT_PATIENT_NAMES.get(lang_key, DEFAULT_PATIENT_NAMES["en-US"])
    return persona_map.get(persona.lower(), persona_map.get("default", "Mukul Sharma"))


def _generate_dental_room_name(scenario: str, patient_name: str) -> str:
    """Generates a unique room name for dental training: DENTAL-{CleanScenario}-{CleanName}-{uuid_short}."""
    clean_scenario = scenario.replace("dental_", "").replace("_", "-").capitalize()
    clean_name = "".join(ch for ch in patient_name if ch.isalnum())
    short_id = uuid.uuid4().hex[:6]
    return f"DENTAL-{clean_scenario}-{clean_name}-{short_id}"


class IAutoCoachService(ABC):
    """
    Interface for AutoCoach session lifecycle and agent dispatch orchestration.
    """
    @abstractmethod
    async def create_and_dispatch_session(
        self, session_in: AutoCoachSessionCreate
    ) -> AutoCoachSessionResponse:
        """
        Creates a LiveKit room, dispatches the AutoCoach agent worker, waits
        for the agent-first handshake, and returns the room token to the frontend.
        """
        pass

    @abstractmethod
    async def list_sessions(self) -> List[RoomResponse]:
        """Lists active dental training simulation rooms."""
        pass

    @abstractmethod
    async def get_session(self, room_name: str) -> Optional[RoomResponse]:
        """Gets room status and active participants for a specific session."""
        pass

    @abstractmethod
    async def delete_session(self, room_name: str) -> bool:
        """Closes and tears down an AutoCoach session room."""
        pass

    @abstractmethod
    def generate_token(
        self, room_name: str, token_req: AutoCoachTokenRequest
    ) -> TokenResponse:
        """Generates a participant or observer token for an active AutoCoach room."""
        pass


class LiveKitAutoCoachService(IAutoCoachService):
    """
    LiveKit-backed implementation of IAutoCoachService.
    Uses the STS LiveKit client to dispatch and monitor the AutoCoach agent worker.
    """
    def __init__(self, lk_client: api.LiveKitAPI):
        self.client = lk_client

    async def create_and_dispatch_session(
        self, session_in: AutoCoachSessionCreate
    ) -> AutoCoachSessionResponse:
        patient_name = _resolve_patient_name(
            language=session_in.language or "en-US",
            persona=session_in.persona or "default",
            requested_name=session_in.patient_name,
        )
        room_name = _generate_dental_room_name(
            scenario=session_in.scenario or "dental_scheduling",
            patient_name=patient_name,
        )

        trainee_id = session_in.trainee_id or f"trainee_{uuid.uuid4().hex[:4]}"
        trainee_name = session_in.trainee_name or "Front Desk Trainee"

        # Build structured metadata matching AutoCoach prompt engine and reporting expectations
        metadata = {
            "scenario": session_in.scenario or "dental_scheduling",
            "persona": session_in.persona or "default",
            "persona_name": patient_name,
            "language": session_in.language or "en-US",
            "difficulty": session_in.difficulty or "medium",
            "name": patient_name,
            "patient_name": patient_name,
            "customer_name": patient_name,
            "trainee_id": trainee_id,
            "trainee_name": trainee_name,
        }
        if session_in.gender:
            metadata["gender"] = session_in.gender
        if session_in.voice:
            metadata["voice"] = session_in.voice
        if session_in.custom_instructions:
            metadata["custom_instructions"] = session_in.custom_instructions
        if session_in.reports_webhook_url:
            metadata["reports_webhook_url"] = session_in.reports_webhook_url
        if session_in.extra_metadata:
            metadata.update(session_in.extra_metadata)

        metadata_json = json.dumps(metadata)

        # 1. Create Room in LiveKit
        logger.info(
            f"Creating AutoCoach dental room: {room_name} "
            f"(scenario={session_in.scenario}, lang={session_in.language}, patient='{patient_name}')"
        )
        create_request = api.CreateRoomRequest(
            name=room_name,
            empty_timeout=session_in.empty_timeout or 300,
            max_participants=session_in.max_participants or 5,
            metadata=metadata_json,
        )
        room_info = await self.client.room.create_room(create_request)

        # 2. Dispatch the AutoCoach Agent Worker explicitly
        agent_name = session_in.agent_name or "autocoach-customer-sts"
        logger.info(f"Triggering explicit agent dispatch for '{agent_name}' in room '{room_name}'")
        try:
            dispatch_request = api.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=metadata_json,
            )
            await self.client.agent_dispatch.create_dispatch(dispatch_request)
            logger.info(f"Dispatch request sent successfully for '{agent_name}' in room '{room_name}'")
        except Exception as e:
            logger.error(f"Failed to dispatch agent '{agent_name}' to room '{room_name}': {e}", exc_info=True)
            # Clean up the empty room on dispatch error
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to dispatch agent worker '{agent_name}': {str(e)}",
            )

        # 3. Agent-First Handshake: Wait until agent worker is confirmed active in the room
        wait_timeout = session_in.wait_timeout_seconds or 10.0
        poll_interval = 0.35  # 350ms
        max_attempts = max(1, int(wait_timeout / poll_interval))

        logger.info(
            f"Awaiting agent handshake in room '{room_name}' "
            f"(timeout={wait_timeout}s, interval={poll_interval}s)..."
        )

        agent_confirmed = False
        agent_identity: Optional[str] = None

        for attempt in range(max_attempts):
            try:
                part_request = api.ListParticipantsRequest(room=room_name)
                part_response = await self.client.room.list_participants(part_request)

                for p in part_response.participants:
                    if self._is_agent_participant(p, agent_name):
                        agent_confirmed = True
                        agent_identity = p.identity
                        logger.info(
                            f"Agent verified in room '{room_name}' on attempt {attempt + 1}: "
                            f"identity='{agent_identity}', name='{p.name}'"
                        )
                        break

                if agent_confirmed:
                    break
            except Exception as e:
                logger.debug(f"Transient error querying participants for '{room_name}': {e}")

            await asyncio.sleep(poll_interval)

        # 4. If agent failed to join within timeout, abort cleanly to prevent empty room lock
        if not agent_confirmed:
            logger.warning(
                f"Agent handshake timed out for room '{room_name}' after {wait_timeout}s. "
                f"Agent worker '{agent_name}' did not join."
            )
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception as e:
                logger.error(f"Failed to delete room '{room_name}' after timeout: {e}")

            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=(
                    f"Agent dispatch handshake timed out: Worker '{agent_name}' did not join room '{room_name}' "
                    f"within {wait_timeout} seconds. Please verify the AutoCoach agent worker process is running and connected."
                ),
            )

        # 5. Agent is verified in the room! Generate the Trainee's JWT access token
        trainee_identity = f"trainee-{trainee_id}"
        token = self._build_trainee_token(
            room_name=room_name,
            identity=trainee_identity,
            name=trainee_name,
        )

        logger.info(
            f"Handshake complete for '{room_name}'. Frontend granted entry as '{trainee_identity}'."
        )

        return AutoCoachSessionResponse(
            room_name=room_info.name,
            room_sid=room_info.sid,
            livekit_url=settings.STS_LIVEKIT_URL,
            token=token,
            identity=trainee_identity,
            agent_status="ready",
            agent_identity=agent_identity,
            scenario=session_in.scenario or "dental_scheduling",
            language=session_in.language or "en-US",
            patient_name=patient_name,
        )

    async def list_sessions(self) -> List[RoomResponse]:
        """Lists active dental training simulation rooms."""
        logger.info("Listing active AutoCoach dental simulation rooms")
        request = api.ListRoomsRequest()
        response = await self.client.room.list_rooms(request)

        sessions = []
        for room_info in response.rooms:
            # Filter rooms belonging to AutoCoach
            if not room_info.name.startswith("DENTAL-"):
                # Also check metadata if prefixed differently
                if not (room_info.metadata and "dental" in room_info.metadata.lower()):
                    continue

            sessions.append(
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
        return sessions

    async def get_session(self, room_name: str) -> Optional[RoomResponse]:
        """Gets details and active participants for a specific AutoCoach room."""
        logger.info(f"Retrieving AutoCoach session details for: {room_name}")
        list_request = api.ListRoomsRequest(names=[room_name])
        list_response = await self.client.room.list_rooms(list_request)

        if not list_response.rooms:
            logger.warning(f"AutoCoach room '{room_name}' not found")
            return None

        room_info = list_response.rooms[0]

        # Fetch participants
        part_request = api.ListParticipantsRequest(room=room_name)
        part_response = await self.client.room.list_participants(part_request)

        active_participants = []
        for p in part_response.participants:
            attrs = dict(p.attributes) if hasattr(p, "attributes") else {}
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

    async def delete_session(self, room_name: str) -> bool:
        """Tears down an AutoCoach session room."""
        logger.info(f"Closing AutoCoach session room: {room_name}")
        try:
            request = api.DeleteRoomRequest(room=room_name)
            await self.client.room.delete_room(request)
            return True
        except Exception as e:
            logger.error(f"Error deleting AutoCoach room '{room_name}': {e}")
            return False

    def generate_token(
        self, room_name: str, token_req: AutoCoachTokenRequest
    ) -> TokenResponse:
        """Generates a trainee or supervisor JWT token for an active AutoCoach room."""
        logger.info(f"Generating AutoCoach token for {token_req.identity} in room {room_name}")
        jwt_token = self._build_trainee_token(
            room_name=room_name,
            identity=token_req.identity,
            name=token_req.name,
        )
        return TokenResponse(
            token=jwt_token,
            room_name=room_name,
            identity=token_req.identity,
        )

    @staticmethod
    def _is_agent_participant(participant: api.ParticipantInfo, expected_agent_name: str) -> bool:
        """Checks if a participant represents the active Agent worker."""
        # 1. Protobuf Kind check (Kind.AGENT == 2)
        if hasattr(participant, "kind"):
            kind_val = str(participant.kind).upper()
            if kind_val in ["2", "AGENT", "PARTICIPANTINFO.KIND.AGENT"]:
                return True

        # 2. Identity or name pattern check
        ident = (participant.identity or "").lower()
        p_name = (participant.name or "").lower()
        expected = expected_agent_name.lower()

        if expected in ident or expected in p_name:
            return True
        if ident.startswith("agent-") or ident.startswith("agent_") or "autocoach" in ident:
            return True

        return False

    @staticmethod
    def _build_trainee_token(
        room_name: str, identity: str, name: Optional[str] = None
    ) -> str:
        """Builds a signed LiveKit JWT token granting mic audio publishing and subscription."""
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

        if name:
            token.with_name(name)

        return token.to_jwt()
