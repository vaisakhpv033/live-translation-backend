"""
Pydantic Schemas for Stage 4: Appointment Action Verification
Validates that appointment cancellations and reschedules performed during a training call
align with real Open Dental data (slot availability, patient identity, appointment reference).
"""

from typing import Optional
from pydantic import BaseModel, Field


class SuggestedSlot(BaseModel):
    """A slot the trainee suggested during the call (extracted by Gemini)."""
    date: Optional[str] = Field(default=None, description="Suggested date in YYYY-MM-DD format")
    time: Optional[str] = Field(default=None, description="Suggested time in HH:MM format")
    provider: Optional[str] = Field(default=None, description="Provider name, e.g. 'Dr. Gupta'")
    raw_text: str = Field(default="", description="Exact quote from the transcript where the slot was mentioned")


class TranscriptOutcome(BaseModel):
    """What happened during the call (extracted by Gemini)."""
    cancellation_confirmed: bool = Field(default=False, description="Whether the trainee confirmed the cancellation")
    cancellation_reason_captured: bool = Field(default=False, description="Whether the trainee captured a reason for cancellation")
    reason_for_cancellation: Optional[str] = Field(default=None, description="The cancellation reason stated by the patient")
    reschedule_confirmed: bool = Field(default=False, description="Whether the trainee confirmed a reschedule")
    slots_suggested: list[SuggestedSlot] = Field(default_factory=list, description="All appointment slots the trainee offered")
    final_agreed_slot: Optional[SuggestedSlot] = Field(default=None, description="The slot both parties agreed upon")
    correct_patient_verified: bool = Field(default=False, description="Whether the trainee verified the correct patient identity")
    correct_appointment_referenced: bool = Field(default=False, description="Whether the trainee referenced the correct original appointment")
    summary: str = Field(default="", description="Brief factual summary of what happened on the call")


class SlotAvailabilityResult(BaseModel):
    """Result of checking a suggested slot against Open Dental."""
    suggested_slot: SuggestedSlot = Field(description="The slot that was checked")
    is_available: bool = Field(description="Whether the suggested time falls within an available OD slot window")
    matching_od_slots: list[dict] = Field(default_factory=list, description="Open Dental slot windows that match")
    explanation: str = Field(default="", description="Human-readable explanation of the availability check")


class AppointmentActionVerdict(BaseModel):
    """Final verification result for a cancel or reschedule action."""
    call_type: str = Field(description="Type of action: 'cancel' or 'reschedule'")
    verification_status: str = Field(description="Overall result: 'pass' | 'fail' | 'partial' | 'error'")
    original_apt_num: int = Field(description="AptNum of the original appointment being acted upon")
    original_pat_num: int = Field(description="PatNum of the patient who owns the appointment")
    original_apt_status: Optional[str] = Field(default=None, description="Status of the original appointment in Open Dental")
    original_apt_datetime: Optional[str] = Field(default=None, description="DateTime of the original appointment in Open Dental")
    transcript_outcome: TranscriptOutcome = Field(description="Outcomes extracted from the call transcript")
    slot_checks: list[SlotAvailabilityResult] = Field(default_factory=list, description="Availability results for each suggested slot")
    all_suggested_slots_available: Optional[bool] = Field(default=None, description="True if every suggested slot is available in OD")
    final_slot_available: Optional[bool] = Field(default=None, description="True if the final agreed-upon slot is available in OD")
    checks_passed: list[str] = Field(default_factory=list, description="List of verification check names that passed")
    checks_failed: list[str] = Field(default_factory=list, description="List of verification check names that failed")
    verification_summary: str = Field(description="Human-readable summary of the verification outcome")
