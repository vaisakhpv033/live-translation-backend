from typing import Optional, List, Any, Dict, Union
from pydantic import BaseModel, Field, ConfigDict, model_validator


class PatientSimple(BaseModel):
    """
    Representation of a patient returned by Open Dental GET /patients/Simple.
    """
    PatNum: Union[int, str] = Field(description="Unique patient ID")
    LName: Optional[str] = Field(default="", description="Last Name")
    FName: Optional[str] = Field(default="", description="First Name")
    Preferred: Optional[str] = Field(default=None, description="Preferred Name / Nickname")
    PatStatus: Optional[str] = Field(default="Patient", description="Status: Patient, Inactive, NonPatient, etc.")
    Gender: Optional[str] = Field(default=None, description="Gender: Male, Female, Unknown, Other")
    Position: Optional[str] = Field(default=None, description="Marital status: Single, Married, etc.")
    Birthdate: Optional[str] = Field(default=None, description="Birthdate yyyy-MM-dd")
    WirelessPhone: Optional[str] = Field(default=None, description="Mobile/Cell phone number")
    HmPhone: Optional[str] = Field(default=None, description="Home phone number")
    WkPhone: Optional[str] = Field(default=None, description="Work phone number")
    Email: Optional[str] = Field(default=None, description="Email address")
    Guarantor: Optional[Union[int, str]] = Field(default=None, description="PatNum of the guarantor")
    PriProv: Optional[Union[int, str]] = Field(default=None, description="Primary doctor/provider ID")
    SecProv: Optional[Union[int, str]] = Field(default=None, description="Secondary provider/hygienist ID")
    FeeSched: Optional[Union[int, str]] = Field(default=None, description="Fee schedule ID or name")
    BillingType: Optional[Union[int, str]] = Field(default=None, description="Billing type ID or description")
    ClinicNum: Optional[Union[int, str]] = Field(default=None, description="Clinic branch ID")
    DateTStamp: Optional[str] = Field(default=None, description="Last update timestamp yyyy-MM-dd HH:mm:ss")

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )


class PatientSearchResponse(BaseModel):
    """
    Response model for patient search queries.
    """
    cached: bool = Field(description="Whether result was served from LRU TTL cache")
    count: int = Field(description="Number of patients in this result batch")
    limit: int = Field(description="Max items requested")
    offset: int = Field(description="Pagination offset")
    data: List[PatientSimple] = Field(description="List of matching patient records")


class CacheStatsResponse(BaseModel):
    """
    Metadata about in-memory search cache performance.
    """
    currsize: int = Field(description="Current number of cached queries")
    maxsize: int = Field(description="Maximum capacity of LRU cache")
    ttl: int = Field(description="Time to live in seconds")
    hits: int = Field(description="Total cache hits")
    misses: int = Field(description="Total cache misses")


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


class PatientAppointmentsResponse(BaseModel):
    """
    Response model for patient appointment history and upcoming bookings.
    """
    pat_num: int = Field(description="Patient ID")
    count: int = Field(description="Total number of appointments retrieved")
    cached: bool = Field(default=False, description="Whether result was served from LRU cache")
    appointments: List[AppointmentItem] = Field(default_factory=list, description="List of appointments sorted newest first")
