"""Pydantic V2 schemas for the dedicated USV Doctor Detailing sessions, webhooks, and reports."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UsvDoctorSessionCreate(BaseModel):
    """Request payload for starting a USV Doctor Detailing LiveKit session."""

    agent_name: str = Field(default="ira-voice-agent", description="LiveKit agent worker name")
    scenario: str = Field(default="doctor-detailing", description="Scenario identifier")
    language: str = Field(default="en-IN", description="BCP-47 simulation language")
    patient_name: str = Field(default="Dr. Arthur Hayes", description="Simulated physician name")
    trainee_id: Optional[str] = Field(default="REP-101", description="Medical representative ID")
    trainee_name: Optional[str] = Field(
        default="Medical Sales Representative",
        description="Medical representative display name",
    )
    reports_webhook_url: Optional[str] = Field(
        default=None,
        description="Optional override URL where Autocoach-agent posts post-call telemetry",
    )
    wait_timeout_seconds: Optional[float] = Field(default=10.0, ge=1.0, le=30.0)
    empty_timeout: Optional[int] = Field(default=300)
    max_participants: Optional[int] = Field(default=5)
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Container carrying structured session_config for ira-voice-agent",
    )


class UsvDoctorSessionResponse(BaseModel):
    """Response returned once the agent worker handshake succeeds."""

    room_name: str
    room_sid: str
    livekit_url: str
    token: str
    identity: str
    agent_status: str = "ready"
    agent_identity: Optional[str] = None
    scenario: str
    language: str
    patient_name: Optional[str] = None


class UsvDoctorTokenRequest(BaseModel):
    """Request payload for generating a join token for an existing USV Doctor room."""

    identity: str
    name: Optional[str] = None


class UsvDoctorWebhookPayload(BaseModel):
    """Post-session telemetry payload dispatched by Autocoach-agent's ReportingDispatcher."""

    session_id: Optional[str] = None
    job_id: str
    room_name: Optional[str] = None
    agent: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    ended_at: str
    duration_seconds: Optional[float] = None
    termination_reason: Optional[str] = None
    chat_history: Optional[Any] = None
    model_usage: Optional[List[Dict[str, Any]]] = None
    events: Optional[List[Dict[str, Any]]] = None
    audio_recording_path: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class AgentUsageSummary(BaseModel):
    """Normalized LiveKit / Gemini Live voice call token usage metrics."""

    input_tokens: int = 0
    input_cached_tokens: int = 0
    input_text_tokens: int = 0
    input_audio_tokens: int = 0
    output_tokens: int = 0
    output_text_tokens: int = 0
    output_audio_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    raw: Optional[List[Dict[str, Any]]] = None


class QAUsageSummary(BaseModel):
    """Normalized Gemini post-call QA evaluation token usage metrics."""

    model_name: Optional[str] = None
    prompt_tokens: int = 0
    cached_tokens: int = 0
    candidates_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    raw: Optional[Dict[str, Any]] = None


class UsvDoctorReportSummary(BaseModel):
    """Lightweight report summary for dashboard listings."""

    job_id: str
    room: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    overall_score: Optional[int] = None
    status: Optional[str] = None
    customer_name: Optional[str] = None
    sales_rep: Optional[str] = None
    agent_type: Optional[str] = None
    scenario: Optional[str] = None
    doctor_specialty: Optional[str] = None
    readiness_assessment: Optional[str] = None
    agent_total_tokens: int = 0
    qa_total_tokens: int = 0
    agent_cost_usd: float = 0.0
    qa_cost_usd: float = 0.0
    total_cost_usd: float = 0.0


class UsvDoctorReportDetail(BaseModel):
    """Full USV Doctor Detailing report detail including transcript, QA scorecard, and usage metrics."""

    job_id: str
    session_id: Optional[str] = None
    room_id: Optional[str] = None
    room: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    termination_reason: Optional[str] = None
    summary: Optional[Any] = None
    overall_score: Optional[int] = None
    status: Optional[str] = None
    customer_name: Optional[str] = None
    agent_type: Optional[str] = None
    sales_rep: Optional[str] = None
    trainee_id: Optional[str] = None
    scenario: Optional[str] = None
    title: Optional[str] = None
    doctor_specialty: Optional[str] = None
    clinic_setting: Optional[str] = None
    demeanor: Optional[str] = None
    model_name: Optional[str] = None
    language: Optional[str] = None
    voice_id: Optional[str] = None
    chat_history: Optional[Any] = None
    events: Optional[Any] = None
    agent_usage: Optional[AgentUsageSummary] = None
    qa_usage: Optional[QAUsageSummary] = None
    total_cost_usd: float = 0.0
    created_at: Optional[str] = None


class UsvDoctorReportListResponse(BaseModel):
    """List response with aggregate score, readiness, and token usage statistics."""

    reports: List[UsvDoctorReportSummary]
    stats: Dict[str, Any] = Field(default_factory=dict)
