from pydantic import BaseModel, Field
from typing import Optional, Any


class ReportCreate(BaseModel):
    """
    Payload received from the STS agent on session end.
    Mirrors the report-server's ReportPayload schema.
    """
    job_id: str = Field(..., description="Unique job identifier from LiveKit")
    room_id: str = Field(..., description="LiveKit room SID")
    room: str = Field(..., description="Human-readable room name")
    started_at: Optional[str] = Field(None, description="ISO timestamp of call start")
    ended_at: str = Field(..., description="ISO timestamp of call end")
    summary: Optional[Any] = Field(None, description="Optional pre-computed summary (dict or string)")
    chat_history: Optional[dict] = Field(None, description="LiveKit chat history object")
    customer_name: Optional[str] = Field(None, description="Customer name")
    agent_type: Optional[str] = Field(None, description="Agent type identifier")
    sales_rep: Optional[str] = Field(None, description="Sales representative name")
    scenario: Optional[str] = Field(None, description="Evaluation scenario (sbi, wtw)")


class ReportSummary(BaseModel):
    """
    Lightweight report item for listings.
    """
    job_id: str
    room: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    overall_score: Optional[int] = None
    status: Optional[str] = None
    customer_name: Optional[str] = None
    agent_type: Optional[str] = None
    scenario: Optional[str] = None


class ReportDetail(BaseModel):
    """
    Full report detail including chat history and evaluation summary.
    """
    job_id: str
    room_id: Optional[str] = None
    room: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    summary: Optional[Any] = None
    overall_score: Optional[int] = None
    chat_history: Optional[Any] = None
    status: Optional[str] = None
    customer_name: Optional[str] = None
    agent_type: Optional[str] = None
    sales_rep: Optional[str] = None
    scenario: Optional[str] = None
    created_at: Optional[str] = None


class ReportListResponse(BaseModel):
    """
    Response containing a list of reports with aggregate statistics.
    """
    reports: list[ReportSummary]
    stats: dict = Field(default_factory=dict, description="Aggregate statistics across reports")
