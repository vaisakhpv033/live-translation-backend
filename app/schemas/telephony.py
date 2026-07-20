from pydantic import BaseModel, Field
from typing import Optional, List


# ──────────────────────────────────────────────────────────────
#  Inbound Setup
# ──────────────────────────────────────────────────────────────

class InboundSetupRequest(BaseModel):
    """
    Request to register a Twilio phone number as an inbound SIP trunk
    and create a dispatch rule that routes calls to the Customer-sts agent.
    All fields have sensible defaults from the environment; override only if needed.
    """
    phone_number: Optional[str] = Field(
        None,
        description="Twilio phone number in E.164 format. Defaults to TWILIO_PHONE_NUMBER env var."
    )
    krisp_enabled: bool = Field(
        True,
        description="Enable Krisp noise cancellation for phone audio"
    )


class InboundSetupResponse(BaseModel):
    """Response after inbound trunk + dispatch rule creation."""
    inbound_trunk_id: str = Field(..., description="Created SIP inbound trunk ID")
    dispatch_rule_id: str = Field(..., description="Created SIP dispatch rule ID")
    phone_number: str = Field(..., description="Phone number registered")
    message: str = Field("Inbound trunk and dispatch rule created successfully")


# ──────────────────────────────────────────────────────────────
#  Outbound Trunk Setup
# ──────────────────────────────────────────────────────────────

class OutboundTrunkSetupRequest(BaseModel):
    """
    Request to create an outbound SIP trunk for placing calls via Twilio.
    All fields default from env vars; override only if needed.
    """
    sip_domain: Optional[str] = Field(
        None,
        description="Twilio SIP Termination URI. Defaults to TWILIO_SIP_DOMAIN env var."
    )
    phone_number: Optional[str] = Field(
        None,
        description="Caller ID phone number. Defaults to TWILIO_PHONE_NUMBER env var."
    )
    auth_username: Optional[str] = Field(
        None,
        description="SIP auth username. Defaults to TWILIO_SIP_USERNAME env var."
    )
    auth_password: Optional[str] = Field(
        None,
        description="SIP auth password. Defaults to TWILIO_SIP_PASSWORD env var."
    )


class OutboundTrunkSetupResponse(BaseModel):
    """Response after outbound trunk creation."""
    outbound_trunk_id: str = Field(..., description="Created SIP outbound trunk ID")
    sip_domain: str = Field(..., description="Twilio SIP termination domain configured")
    message: str = Field("Outbound trunk created successfully")


# ──────────────────────────────────────────────────────────────
#  Outbound Call (Dial)
# ──────────────────────────────────────────────────────────────

class OutboundCallRequest(BaseModel):
    """
    Request to initiate an outbound call to a phone number.
    The career-agent persona is hardcoded — no persona selection needed.
    """
    phone_number: str = Field(
        ...,
        description="Destination phone number in E.164 format (e.g. +919876543210)"
    )
    language: str = Field(
        "en",
        description="Language code for the career agent (en, ml, hi, ta, etc.)"
    )
    outbound_trunk_id: Optional[str] = Field(
        None,
        description="Outbound trunk ID to use. If not provided, uses inline trunk config from env vars."
    )


class OutboundCallResponse(BaseModel):
    """Response after initiating an outbound call."""
    room_name: str = Field(..., description="LiveKit room name where the call is happening")
    participant_identity: str = Field(..., description="Identity of the SIP participant in the room")
    call_status: str = Field(..., description="Current SIP call status (e.g. dialing, active)")
    message: str = Field("Outbound call initiated successfully")


# ──────────────────────────────────────────────────────────────
#  Call Status
# ──────────────────────────────────────────────────────────────

class ParticipantStatusInfo(BaseModel):
    """Status information for a single participant in a call room."""
    identity: str
    name: str = ""
    state: str = ""
    kind: str = ""
    sip_call_status: Optional[str] = None
    joined_at: Optional[int] = None


class CallStatusResponse(BaseModel):
    """Detailed status of a telephony call room."""
    room_name: str
    room_sid: str = ""
    num_participants: int = 0
    participants: List[ParticipantStatusInfo] = []
    is_active: bool = False


# ──────────────────────────────────────────────────────────────
#  Trunk Listing
# ──────────────────────────────────────────────────────────────

class TrunkInfo(BaseModel):
    """Summary of a configured SIP trunk."""
    trunk_id: str
    name: str = ""
    direction: str = ""  # "inbound" or "outbound"
    numbers: List[str] = []
    address: str = ""


class DispatchRuleInfo(BaseModel):
    """Summary of a configured SIP dispatch rule."""
    rule_id: str
    name: str = ""
    trunk_ids: List[str] = []
    room_prefix: str = ""


class TrunkListResponse(BaseModel):
    """Lists all configured SIP trunks and dispatch rules."""
    inbound_trunks: List[TrunkInfo] = []
    outbound_trunks: List[TrunkInfo] = []
    dispatch_rules: List[DispatchRuleInfo] = []
