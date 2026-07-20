import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional
from livekit import api
from app.schemas.telephony import (
    InboundSetupRequest, InboundSetupResponse,
    OutboundTrunkSetupRequest, OutboundTrunkSetupResponse,
    OutboundCallRequest, OutboundCallResponse,
    CallStatusResponse, ParticipantStatusInfo,
    TrunkListResponse, TrunkInfo, DispatchRuleInfo,
)
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.services.telephony_service")
settings = get_settings()

# Fixed persona for all telephony calls
TELEPHONY_PERSONA = "career-agent"
TELEPHONY_AGENT_NAME = "Customer-sts"


class ITelephonyService(ABC):
    """
    Interface for telephony operations (Interface Segregation).
    All telephony SIP management flows through this abstraction.
    """

    @abstractmethod
    async def setup_inbound(self, request: InboundSetupRequest) -> InboundSetupResponse:
        """One-time: registers Twilio number as inbound trunk + creates dispatch rule."""
        pass

    @abstractmethod
    async def setup_outbound_trunk(self, request: OutboundTrunkSetupRequest) -> OutboundTrunkSetupResponse:
        """One-time: creates a stored outbound trunk for placing calls."""
        pass

    @abstractmethod
    async def make_outbound_call(self, request: OutboundCallRequest) -> OutboundCallResponse:
        """Dispatches the career agent + dials a phone number."""
        pass

    @abstractmethod
    async def get_call_status(self, room_name: str) -> CallStatusResponse:
        """Gets SIP participant status in a call room."""
        pass

    @abstractmethod
    async def list_trunks(self) -> TrunkListResponse:
        """Lists configured SIP trunks and dispatch rules."""
        pass

    @abstractmethod
    async def hangup_call(self, room_name: str) -> bool:
        """Terminates an active call by closing the room."""
        pass


class LiveKitTelephonyService(ITelephonyService):
    """
    Implementation of ITelephonyService using the LiveKitAPI SIP service (Dependency Inversion).
    Hardcodes the career-agent persona for all telephony calls.
    """

    def __init__(self, lk_client: api.LiveKitAPI):
        self.client = lk_client

    async def setup_inbound(self, request: InboundSetupRequest) -> InboundSetupResponse:
        phone_number = request.phone_number or settings.TWILIO_PHONE_NUMBER
        if not phone_number:
            raise ValueError("No phone number provided and TWILIO_PHONE_NUMBER env var is empty")

        # Check for existing inbound trunks to avoid duplicates (idempotent)
        existing = await self.client.sip.list_sip_inbound_trunk(
            api.ListSIPInboundTrunkRequest()
        )
        for trunk in existing.items:
            if phone_number in list(trunk.numbers):
                logger.info(f"Inbound trunk already exists for {phone_number}: {trunk.sip_trunk_id}")
                # Check if dispatch rule also exists
                rules = await self.client.sip.list_sip_dispatch_rule(
                    api.ListSIPDispatchRuleRequest()
                )
                for rule in rules.items:
                    if trunk.sip_trunk_id in list(rule.trunk_ids):
                        return InboundSetupResponse(
                            inbound_trunk_id=trunk.sip_trunk_id,
                            dispatch_rule_id=rule.sip_dispatch_rule_id,
                            phone_number=phone_number,
                            message="Inbound trunk and dispatch rule already exist (idempotent)"
                        )

        # 1. Create inbound trunk
        logger.info(f"Creating inbound trunk for {phone_number}")
        trunk_info = api.SIPInboundTrunkInfo(
            name="twilio-inbound",
            numbers=[phone_number],
            krisp_enabled=request.krisp_enabled,
        )
        created_trunk = await self.client.sip.create_sip_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(trunk=trunk_info)
        )
        inbound_trunk_id = created_trunk.sip_trunk_id
        logger.info(f"Created inbound trunk: {inbound_trunk_id}")

        # 2. Create dispatch rule that routes to Customer-sts with career-agent persona
        rule = api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                room_prefix="sip-inbound-",
            )
        )
        room_config = api.RoomConfiguration(
            empty_timeout=300,
            max_participants=3,
        )
        agent_dispatch = room_config.agents.add()
        agent_dispatch.agent_name = TELEPHONY_AGENT_NAME
        agent_dispatch.metadata = json.dumps({
            "persona": TELEPHONY_PERSONA,
            "language": "en",
        })

        created_rule = await self.client.sip.create_sip_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(
                rule=rule,
                trunk_ids=[inbound_trunk_id],
                name="career-agent-inbound-dispatch",
                room_config=room_config,
            )
        )
        dispatch_rule_id = created_rule.sip_dispatch_rule_id
        logger.info(f"Created dispatch rule: {dispatch_rule_id}")

        return InboundSetupResponse(
            inbound_trunk_id=inbound_trunk_id,
            dispatch_rule_id=dispatch_rule_id,
            phone_number=phone_number,
        )

    async def setup_outbound_trunk(self, request: OutboundTrunkSetupRequest) -> OutboundTrunkSetupResponse:
        sip_domain = request.sip_domain or settings.TWILIO_SIP_DOMAIN
        phone_number = request.phone_number or settings.TWILIO_PHONE_NUMBER
        auth_username = request.auth_username or settings.TWILIO_SIP_USERNAME
        auth_password = request.auth_password or settings.TWILIO_SIP_PASSWORD

        if not sip_domain:
            raise ValueError("No SIP domain provided and TWILIO_SIP_DOMAIN env var is empty")

        # Check for existing outbound trunks to avoid duplicates
        existing = await self.client.sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest()
        )
        for trunk in existing.items:
            if trunk.address == sip_domain:
                logger.info(f"Outbound trunk already exists for {sip_domain}: {trunk.sip_trunk_id}")
                return OutboundTrunkSetupResponse(
                    outbound_trunk_id=trunk.sip_trunk_id,
                    sip_domain=sip_domain,
                    message="Outbound trunk already exists (idempotent)"
                )

        logger.info(f"Creating outbound trunk for {sip_domain}")
        trunk_info = api.SIPOutboundTrunkInfo(
            name="twilio-outbound",
            address=sip_domain,
            numbers=[phone_number] if phone_number else [],
            auth_username=auth_username,
            auth_password=auth_password,
            transport=api.SIP_TRANSPORT_TCP,
        )
        created_trunk = await self.client.sip.create_sip_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(trunk=trunk_info)
        )
        logger.info(f"Created outbound trunk: {created_trunk.sip_trunk_id}")

        return OutboundTrunkSetupResponse(
            outbound_trunk_id=created_trunk.sip_trunk_id,
            sip_domain=sip_domain,
        )

    async def make_outbound_call(self, request: OutboundCallRequest) -> OutboundCallResponse:
        # Generate unique room name
        short_id = uuid.uuid4().hex[:8]
        room_name = f"sip-outbound-career-{short_id}"

        # Build metadata for the career-agent persona
        metadata = json.dumps({
            "persona": TELEPHONY_PERSONA,
            "language": request.language,
        })

        # 1. Dispatch the Customer-sts agent to the room
        logger.info(f"Dispatching {TELEPHONY_AGENT_NAME} to room {room_name}")
        await self.client.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=TELEPHONY_AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )

        # 2. Create SIP participant (dial the phone number)
        participant_identity = f"phone-{uuid.uuid4().hex[:6]}"

        # Determine trunk configuration
        if request.outbound_trunk_id:
            # Use stored trunk
            logger.info(f"Dialing {request.phone_number} via stored trunk {request.outbound_trunk_id}")
            sip_request = api.CreateSIPParticipantRequest(
                sip_trunk_id=request.outbound_trunk_id,
                sip_call_to=request.phone_number,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name="Phone Caller",
                krisp_enabled=True,
                play_dialtone=True,
            )
        else:
            # Use inline trunk from env vars
            sip_domain = settings.TWILIO_SIP_DOMAIN
            if not sip_domain:
                raise ValueError("No outbound_trunk_id provided and TWILIO_SIP_DOMAIN env var is empty")

            logger.info(f"Dialing {request.phone_number} via inline trunk ({sip_domain})")
            sip_request = api.CreateSIPParticipantRequest(
                trunk=api.SIPOutboundConfig(
                    hostname=sip_domain,
                    auth_username=settings.TWILIO_SIP_USERNAME,
                    auth_password=settings.TWILIO_SIP_PASSWORD,
                    transport=api.SIP_TRANSPORT_TCP,
                ),
                sip_call_to=request.phone_number,
                sip_number=settings.TWILIO_PHONE_NUMBER,  # Caller ID
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name="Phone Caller",
                krisp_enabled=True,
                play_dialtone=True,
            )

        try:
            participant_info = await self.client.sip.create_sip_participant(sip_request)
            logger.info(f"SIP participant created in room {room_name}: {participant_identity}")
            return OutboundCallResponse(
                room_name=room_name,
                participant_identity=participant_identity,
                call_status="dialing",
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to create SIP participant: {error_msg}")
            # Try to clean up the room on failure
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            raise ValueError(f"SIP call failed: {error_msg}")

    async def get_call_status(self, room_name: str) -> CallStatusResponse:
        # Check if room exists
        list_response = await self.client.room.list_rooms(
            api.ListRoomsRequest(names=[room_name])
        )
        if not list_response.rooms:
            return CallStatusResponse(
                room_name=room_name,
                is_active=False,
            )

        room_info = list_response.rooms[0]

        # Get participants
        part_response = await self.client.room.list_participants(
            api.ListParticipantsRequest(room=room_name)
        )

        participants = []
        for p in part_response.participants:
            attrs = dict(p.attributes) if hasattr(p, "attributes") else {}
            participants.append(ParticipantStatusInfo(
                identity=p.identity,
                name=p.name,
                state=str(p.state),
                kind=str(p.kind) if hasattr(p, "kind") else "",
                sip_call_status=attrs.get("sip.callStatus"),
                joined_at=p.joined_at,
            ))

        return CallStatusResponse(
            room_name=room_name,
            room_sid=room_info.sid,
            num_participants=room_info.num_participants,
            participants=participants,
            is_active=True,
        )

    async def list_trunks(self) -> TrunkListResponse:
        # List inbound trunks
        inbound_response = await self.client.sip.list_sip_inbound_trunk(
            api.ListSIPInboundTrunkRequest()
        )
        inbound_trunks = [
            TrunkInfo(
                trunk_id=t.sip_trunk_id,
                name=t.name,
                direction="inbound",
                numbers=list(t.numbers),
            )
            for t in inbound_response.items
        ]

        # List outbound trunks
        outbound_response = await self.client.sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest()
        )
        outbound_trunks = [
            TrunkInfo(
                trunk_id=t.sip_trunk_id,
                name=t.name,
                direction="outbound",
                numbers=list(t.numbers),
                address=t.address,
            )
            for t in outbound_response.items
        ]

        # List dispatch rules
        rules_response = await self.client.sip.list_sip_dispatch_rule(
            api.ListSIPDispatchRuleRequest()
        )
        dispatch_rules = []
        for r in rules_response.items:
            room_prefix = ""
            if r.rule and r.rule.dispatch_rule_individual:
                room_prefix = r.rule.dispatch_rule_individual.room_prefix
            dispatch_rules.append(DispatchRuleInfo(
                rule_id=r.sip_dispatch_rule_id,
                name=r.name,
                trunk_ids=list(r.trunk_ids),
                room_prefix=room_prefix,
            ))

        return TrunkListResponse(
            inbound_trunks=inbound_trunks,
            outbound_trunks=outbound_trunks,
            dispatch_rules=dispatch_rules,
        )

    async def hangup_call(self, room_name: str) -> bool:
        logger.info(f"Hanging up call in room: {room_name}")
        try:
            await self.client.room.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to hang up call in room {room_name}: {e}")
            return False
