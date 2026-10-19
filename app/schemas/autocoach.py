from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List


class AutoCoachSessionCreate(BaseModel):
    """
    Request model for initiating a new AutoCoach training simulation session.
    Dispatches the AutoCoach agent worker to a LiveKit room and waits for handshake
    before issuing a join token to the frontend trainee.
    """
    scenario: Optional[str] = Field(
        default="dental_scheduling",
        description="Dental training scenario (e.g. dental_scheduling, dental_emergency, dental_price_shopper, dental_insurance_verification, dental_implant_consult, dental_records_transfer)"
    )
    language: Optional[str] = Field(
        default="en-US",
        description="Target simulation language: 'en-US' (US English), 'es-US' (US Spanish), or 'code-mixed' / 'es-en' (Spanglish)"
    )
    patient_name: Optional[str] = Field(
        default=None,
        description="Custom patient name for the simulated caller"
    )
    persona: Optional[str] = Field(
        default="default",
        description="Caller persona archetype (e.g. default, skeptical, angry, confused, demanding, anxious)"
    )
    difficulty: Optional[str] = Field(
        default="medium",
        description="Simulation objection severity: 'easy', 'medium', 'hard', or 'nightmare'"
    )
    gender: Optional[str] = Field(
        default=None,
        description="Patient caller gender: 'male' or 'female' (used to resolve matching natural Gemini voice)"
    )
    voice: Optional[str] = Field(
        default=None,
        description="Gemini 3.8 Live voice override (e.g. Puck, Charon, Aoede, Fenrir, Kore)"
    )
    custom_instructions: Optional[str] = Field(
        default=None,
        description="Specific clinical or situational instructions injected into the customer prompt"
    )
    trainee_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the trainee"
    )
    trainee_name: Optional[str] = Field(
        default="Front Desk Trainee",
        description="Human-readable name of the representative/trainee"
    )
    reports_webhook_url: Optional[str] = Field(
        default=None,
        description="Optional override URL where the agent will post the post-call report"
    )
    agent_name: Optional[str] = Field(
        default="autocoach-customer-sts",
        description="Target LiveKit agent worker name registered in the cluster"
    )
    wait_timeout_seconds: Optional[float] = Field(
        default=10.0,
        ge=1.0,
        le=30.0,
        description="Maximum seconds to wait for the agent worker to join the room before timing out"
    )
    empty_timeout: Optional[int] = Field(
        default=300,
        description="Room auto-close timeout in seconds once all participants leave"
    )
    max_participants: Optional[int] = Field(
        default=5,
        description="Maximum participants allowed in the training room"
    )
    extra_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary additional metadata forwarded to ctx.job.metadata"
    )


class AutoCoachSessionResponse(BaseModel):
    """
    Response returned to the frontend once the AutoCoach agent has successfully joined the room.
    Grants the frontend immediate, verified permission to enter.
    """
    room_name: str = Field(description="Generated LiveKit room name")
    room_sid: str = Field(description="Unique LiveKit room SID")
    livekit_url: str = Field(description="WebSocket URL for the LiveKit server")
    token: str = Field(description="Signed JWT access token for the trainee")
    identity: str = Field(description="Assigned participant identity for the trainee")
    agent_status: str = Field(default="ready", description="Agent presence status: 'ready'")
    agent_identity: Optional[str] = Field(default=None, description="Identity of the confirmed agent worker in the room")
    scenario: str = Field(description="Active dental training scenario")
    language: str = Field(description="Active simulation language")
    patient_name: Optional[str] = Field(default=None, description="Simulated patient name")


class AutoCoachTokenRequest(BaseModel):
    """
    Request model for generating an additional or refreshed token for an existing AutoCoach room.
    """
    identity: str = Field(description="Unique participant identity (e.g. trainee-01 or supervisor-01)")
    name: Optional[str] = Field(default=None, description="Display name for the participant")


class AutoCoachReportPayload(BaseModel):
    """
    Payload received from the AutoCoach agent worker upon session termination.
    Supports both native AutoCoach telemetry and standard report fields.
    """
    job_id: str = Field(description="LiveKit job ID or unique session identifier")
    room_name: Optional[str] = Field(default=None, description="LiveKit room name")
    room_id: Optional[str] = Field(default=None, description="Room SID or name")
    session_id: Optional[str] = Field(default=None, description="Simulation session identifier")
    started_at: Optional[str] = Field(default=None, description="ISO timestamp of call start")
    ended_at: str = Field(description="ISO timestamp of call end")
    duration_seconds: Optional[float] = Field(default=None, description="Call duration in seconds")
    trainee: Optional[Dict[str, Any]] = Field(default=None, description="Trainee details (id, name)")
    simulation: Optional[Dict[str, Any]] = Field(default=None, description="Simulation metadata (scenario, persona, language)")
    evaluation_rubric: Optional[Dict[str, Any]] = Field(default=None, description="Optional custom rubric")
    termination: Optional[Dict[str, Any]] = Field(default=None, description="Call termination reason and timestamp")
    chat_history: Optional[Any] = Field(default=None, description="Full transcript messages and telemetry")
    extra_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional context metadata")
    scenario: Optional[str] = Field(default=None, description="Explicit scenario name fallback")
    customer_name: Optional[str] = Field(default=None, description="Patient name fallback")
