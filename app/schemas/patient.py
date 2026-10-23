from typing import Optional, List, Any, Dict, Union
from pydantic import BaseModel, Field, ConfigDict


class PatientSimple(BaseModel):
    """
    Representation of a patient returned by Open Dental GET /patients/Simple.
    """
    PatNum: Union[int, str] = Field(description="Unique patient ID")
    LName: Optional[str] = Field(default="", description="Last Name")
    FName: Optional[str] = Field(default="", description="First Name")
    Preferred: Optional[str] = Field(default=None, description="Preferred Name / Nickname")
    PatStatus: Optional[str] = Field(default="Patient", description="Status (Patient, Inactive, NonPatient, etc.)")
    Gender: Optional[str] = Field(default=None, description="Gender (Male, Female, Unknown, Other)")
    Position: Optional[str] = Field(default=None, description="Marital status (Single, Married, etc.)")
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
