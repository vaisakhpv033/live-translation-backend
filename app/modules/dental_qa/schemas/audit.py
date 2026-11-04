"""
Pydantic Schemas for Stage 1 Audits (Dental SOP & Clinic Protocol)
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

AuditVerdict = Literal["Adhered", "Partially Adhered", "Violated", "Missed Opportunity"]


class DentalSOPAuditItem(BaseModel):
    sop_id: str = Field(description="Exact rule ID from sop_rules.json (e.g. 'sop_external_xrays')")
    sop_title: str = Field(description="Title of the SOP rule")
    section: str = Field(description="Section category (e.g. 'Reason of Appointment', 'Insurance & Fees')")
    patient_trigger_quote: str = Field(description="Verbatim quote of caller inquiry or objection")
    trainee_actual_quote: str = Field(description="Verbatim quote of trainee's response")
    verdict: AuditVerdict = Field(description="Compliance verdict")
    violation_details: str = Field(description="Explanation of what was missing, breached, or praised")
    approved_sop_verbiage: str = Field(description="Official verbiage guideline from the SOP")


class DentalSOPAuditResponse(BaseModel):
    dental_sop_adherence_score: int = Field(ge=1, le=10, description="Raw 1-10 score for dental SOP adherence")
    dental_sop_adherence_reason: str = Field(description="Summary justification for the SOP adherence score")
    sop_audit_table: List[DentalSOPAuditItem] = Field(default_factory=list, description="List of triggered SOP items")


class ClinicProtocolAuditItem(BaseModel):
    rule_id: str = Field(description="Exact rule ID from clinic protocol (e.g. 'citrus_10_f_hours')")
    rule_title: str = Field(description="Title of the clinic protocol rule")
    section: str = Field(description="Protocol section (e.g. 'Practice Identification', 'Financial & Payments')")
    patient_trigger_quote: str = Field(description="Verbatim quote of caller inquiry or trigger")
    trainee_actual_quote: str = Field(description="Verbatim quote of trainee's response")
    verdict: AuditVerdict = Field(description="Compliance verdict")
    violation_details: str = Field(description="Specific detail of protocol breach or adherence")
    approved_clinic_rule: str = Field(description="Official directive from the clinic protocol")


class ClinicProtocolAuditResponse(BaseModel):
    clinic_protocol_adherence_score: int = Field(ge=1, le=10, description="Raw 1-10 score for clinic protocol adherence")
    clinic_protocol_adherence_reason: str = Field(description="Summary justification for the clinic protocol score")
    clinic_audit_table: List[ClinicProtocolAuditItem] = Field(default_factory=list, description="List of triggered clinic protocol items")

