from typing import Optional, List, Any, Dict, Union
from pydantic import BaseModel, Field, ConfigDict, model_validator


class AppointmentItem(BaseModel):
    """
    Representation of an appointment returned by Open Dental GET /appointments.
    """
    AptNum: Union[int, str] = Field(description="Unique appointment ID")
    PatNum: Union[int, str] = Field(description="Patient ID")
    AptStatus: Optional[str] = Field(default="Scheduled", description="Appointment status: Scheduled, Complete, Broken, Planned, UnschedList, ASAP")
    AptDateTime: Optional[str] = Field(default=None, description="Appointment date and time yyyy-MM-dd HH:mm:ss")
    ProcDescript: Optional[str] = Field(default="", description="Description of attached procedures")
    Note: Optional[str] = Field(default="", description="Full appointment notes")
    provAbbr: Optional[str] = Field(default="", description="Provider / Doctor abbreviation")
    ProvNum: Optional[Union[int, str]] = Field(default=None, description="Primary provider ID")
    ProvHyg: Optional[Union[int, str]] = Field(default=None, description="Hygienist provider ID")
    Op: Optional[Union[int, str]] = Field(default=None, description="Operatory room ID")
    ClinicNum: Optional[Union[int, str]] = Field(default=None, description="Clinic branch ID")
    Confirmed: Optional[Union[int, str]] = Field(default=None, description="Confirmation definition ID")
    confirmed: Optional[str] = Field(default="", description="Confirmation status text")
    IsNewPatient: Optional[Union[str, bool]] = Field(default="false", description="Whether patient is new")
    IsHygiene: Optional[Union[str, bool]] = Field(default="false", description="Whether hygiene appointment")
    Pattern: Optional[str] = Field(default="", description="Time pattern in 5-minute increments")
    Priority: Optional[str] = Field(default="Normal", description="Priority: Normal, ASAP")
    DateTStamp: Optional[str] = Field(default=None, description="Last update timestamp")

    # Additional operational timestamps from Open Dental
    DateTimeArrived: Optional[str] = Field(default=None, description="Patient check-in arrival time")
    DateTimeSeated: Optional[str] = Field(default=None, description="Patient seated in chair time")
    DateTimeDismissed: Optional[str] = Field(default=None, description="Patient dismissed time")
    InsPlan1: Optional[Union[int, str]] = Field(default=None, description="Primary insurance plan ID")
    InsPlan2: Optional[Union[int, str]] = Field(default=None, description="Secondary insurance plan ID")
    colorOverride: Optional[str] = Field(default="", description="Custom appointment color RGB")
    AppointmentTypeNum: Optional[Union[int, str]] = Field(default=None, description="Appointment type ID")

    # Computed flags for frontend convenience
    is_completed: bool = Field(default=False, description="True if AptStatus is Complete")
    is_scheduled: bool = Field(default=False, description="True if AptStatus is Scheduled")

    @model_validator(mode="after")
    def compute_status_flags(self) -> "AppointmentItem":
        status_lower = (self.AptStatus or "").strip().lower()
        self.is_completed = (status_lower == "complete")
        self.is_scheduled = (status_lower == "scheduled")
        return self

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )


class AppointmentDetailResponse(AppointmentItem):
    """
    Detailed appointment response with optional embedded patient record.
    """
    patient: Optional[Dict[str, Any]] = Field(default=None, description="Full patient record if include_patient=True")
    cached: bool = Field(default=False, description="Whether result was served from LRU cache")


class AppointmentListResponse(BaseModel):
    """
    Response model for appointments query filtered by date or date range.
    """
    count: int = Field(description="Total number of appointments in this result")
    date: Optional[str] = Field(default=None, description="Filtered single date yyyy-MM-dd")
    date_start: Optional[str] = Field(default=None, description="Filtered range start date yyyy-MM-dd")
    date_end: Optional[str] = Field(default=None, description="Filtered range end date yyyy-MM-dd")
    cached: bool = Field(default=False, description="Whether result was served from LRU cache")
    data: List[AppointmentItem] = Field(default_factory=list, description="Appointments sorted chronologically ascending")
