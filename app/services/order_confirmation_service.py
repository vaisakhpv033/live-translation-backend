import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Optional
from livekit import api

from app.schemas.order_confirmation import (
    OrderConfirmationDialRequest,
    OrderConfirmationDialResponse,
)
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.services.order_confirmation_service")
settings = get_settings()

AGENT_NAME = "naaptol-order-confirmation"
AGENT_READINESS_POLL_INTERVAL_S = 0.5
AGENT_READINESS_TIMEOUT_S = 30.0


class IOrderConfirmationService(ABC):
    """
    Interface abstraction for Naaptol Order Confirmation outbound calls (SRP & ISP).
    """

    @abstractmethod
    async def make_outbound_confirmation_call(
        self, request: OrderConfirmationDialRequest
    ) -> OrderConfirmationDialResponse:
        """
        Dispatches the naaptol-order-confirmation agent into the room with order metadata,
        waits for agent readiness to pre-warm WebSockets, and dials the customer's phone number.
        """
        pass


class LiveKitOrderConfirmationService(IOrderConfirmationService):
    """
    Implementation of IOrderConfirmationService using LiveKitAPI SIP & Dispatch services (DIP).
    """

    def __init__(self, lk_client: api.LiveKitAPI):
        self.client = lk_client

    async def _wait_for_agent_ready(self, room_name: str) -> bool:
        """
        Polls room participants until the naaptol-order-confirmation agent worker has joined
        and transitioned to an active state. Eliminates connection/cold-start latency before dialing.
        """
        elapsed = 0.0
        while elapsed < AGENT_READINESS_TIMEOUT_S:
            try:
                part_response = await self.client.room.list_participants(
                    api.ListParticipantsRequest(room=room_name)
                )
                for p in part_response.participants:
                    # State: JOINING=0, JOINED=1, ACTIVE=2, DISCONNECTED=3
                    is_active = p.state in (1, 2)
                    if not is_active:
                        continue

                    p_ident = (p.identity or "").lower()
                    p_name = (p.name or "").lower()
                    p_meta = (p.metadata or "").lower()
                    p_attrs = {str(k).lower(): str(v).lower() for k, v in (p.attributes or {}).items()}

                    is_agent = (
                        "naaptol" in p_name or
                        "orderconfirmation" in p_ident or
                        "naaptol" in p_ident or
                        "naaptol" in p_meta or
                        "naaptol" in p_attrs.get("lk.agent.name", "") or
                        "naaptol" in p_attrs.get("agent_name", "") or
                        p_ident.startswith("agent-")
                    )

                    if is_agent:
                        logger.info(
                            f"Order confirmation agent ready in room '{room_name}': "
                            f"identity={p.identity}, name={p.name}, state={p.state} (waited {elapsed:.1f}s)"
                        )
                        return True
            except Exception as e:
                logger.debug(f"Readiness poll transient check for room {room_name}: {e}")

            await asyncio.sleep(AGENT_READINESS_POLL_INTERVAL_S)
            elapsed += AGENT_READINESS_POLL_INTERVAL_S

        logger.warning(f"Agent readiness timeout after {AGENT_READINESS_TIMEOUT_S}s in room {room_name}")
        return False

    async def make_outbound_confirmation_call(
        self, request: OrderConfirmationDialRequest
    ) -> OrderConfirmationDialResponse:
        short_id = uuid.uuid4().hex[:8]
        room_name = f"sip-outbound-naaptol-{short_id}"

        # Construct comprehensive metadata payload matching OrderDetails schema
        metadata_dict = {
            "customer_name": request.customer_name,
            "Customer Name": request.customer_name,
            "order_id": request.order_id,
            "pkorderid": request.order_id,
            "product_name": request.product_name,
            "Product Name": request.product_name,
            "product_price": request.product_price,
            "productprice": request.product_price,
            "shipping_price": request.shipping_price,
            "Shipping Price": request.shipping_price,
            "total_order_amount": request.total_order_amount,
            "Total Order Amount": request.total_order_amount,
            "expected_delivery_date": request.expected_delivery_date,
            "orderexpecteddeliverydate": request.expected_delivery_date,
            "language": request.language,
        }
        metadata_str = json.dumps(metadata_dict)

        # Step 1: Explicit dispatch of naaptol-order-confirmation agent
        logger.info(f"Dispatching agent '{AGENT_NAME}' to room '{room_name}' with Order ID '{request.order_id}'")
        await self.client.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata_str,
            )
        )

        # Step 2: Wait for agent to be fully connected and standing by (pre-warms WebRTC & Gemini WebSockets)
        logger.info(f"Waiting for agent readiness in room '{room_name}'...")
        agent_ready = await self._wait_for_agent_ready(room_name)

        await asyncio.sleep(90)

        if not agent_ready:
            logger.error(f"Agent worker '{AGENT_NAME}' failed to join room {room_name} in time.")
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            raise ValueError(
                f"Order confirmation agent worker ('{AGENT_NAME}') did not join room within {AGENT_READINESS_TIMEOUT_S}s. "
                "Please verify the agent worker (agent.py) is running."
            )

        # Step 3: Dial customer phone number immediately — agent is already warm and ready
        participant_identity = f"phone-{uuid.uuid4().hex[:6]}"

        if request.outbound_trunk_id:
            logger.info(f"Dialing {request.phone_number} via stored trunk {request.outbound_trunk_id}")
            sip_request = api.CreateSIPParticipantRequest(
                sip_trunk_id=request.outbound_trunk_id,
                sip_call_to=request.phone_number,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name=request.customer_name,
                krisp_enabled=True,
                play_dialtone=False,
            )
        else:
            sip_domain = settings.TWILIO_SIP_DOMAIN
            if not sip_domain:
                raise ValueError("No outbound_trunk_id provided and TWILIO_SIP_DOMAIN env var is empty")

            logger.info(f"Dialing {request.phone_number} via inline Twilio SIP trunk ({sip_domain})")
            sip_request = api.CreateSIPParticipantRequest(
                trunk=api.SIPOutboundConfig(
                    hostname=sip_domain,
                    auth_username=settings.TWILIO_SIP_USERNAME,
                    auth_password=settings.TWILIO_SIP_PASSWORD,
                    transport=api.SIP_TRANSPORT_TCP,
                ),
                sip_call_to=request.phone_number,
                sip_number=settings.TWILIO_PHONE_NUMBER,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name=request.customer_name,
                krisp_enabled=True,
                play_dialtone=False,
            )

        try:
            await self.client.sip.create_sip_participant(sip_request)
            logger.info(f"SIP participant created in room {room_name}: {participant_identity}")
            return OrderConfirmationDialResponse(
                room_name=room_name,
                participant_identity=participant_identity,
                call_status="dialing",
                agent_name=AGENT_NAME,
                order_id=request.order_id,
                customer_name=request.customer_name,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to create SIP participant: {error_msg}")
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            raise ValueError(f"SIP call placement failed: {error_msg}")
