from pydantic import BaseModel, Field
from typing import Optional, Any, List


class CareerDataCreate(BaseModel):
    """
    Payload received from the career-agent on session end.
    """
    job_id: str = Field(..., description="Unique job identifier from LiveKit")
    room_id: str = Field(..., description="LiveKit room SID")
    room: str = Field(..., description="Human-readable room name")
    started_at: Optional[str] = Field(None, description="ISO timestamp of call start")
    ended_at: str = Field(..., description="ISO timestamp of call end")
    summary: Optional[Any] = Field(None, description="Optional pre-computed summary (dict or string)")
    chat_history: Optional[dict] = Field(None, description="LiveKit chat history object")
    customer_name: Optional[str] = Field(None, description="Customer/Student name")
    agent_type: Optional[str] = Field(None, description="Agent type identifier")
    sales_rep: Optional[str] = Field(None, description="Sales representative/Agent name")
    scenario: Optional[str] = Field(None, description="Scenario name")


class CareerRecordDetail(BaseModel):
    """
    Full detail representation of a collected career intake record.
    """
    job_id: str
    room_id: Optional[str] = None
    student_name: Optional[str] = None
    current_status: Optional[str] = None
    next_study_program: Optional[str] = None
    future_goals: Optional[str] = None
    plans_foreign_institutes: Optional[str] = None
    active_search_status: Optional[str] = None
    conviction_tier: Optional[str] = None
    conviction_rationale: Optional[str] = None
    chat_history: Optional[Any] = None
    summary: Optional[Any] = None
    created_at: Optional[str] = None


class CareerRecordListResponse(BaseModel):
    """
    List response of collected student career records.
    """
    records: List[CareerRecordDetail]
