"""
Consolidated Final QA Report Card Schema
Merges Stage 1 audits, Stage 2 behavioral evaluations, and Stage 3 deterministic math.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from .audit import DentalSOPAuditItem, ClinicProtocolAuditItem
from .evaluation import ComplianceSecurityReview

ReadinessTier = str  # "Production Ready" | "Ready With Supervision" | "Developing" | "Needs Significant Coaching" | "Not Ready"


class CallMetadata(BaseModel):
    job_id: str
    clinic_name: str = "Citrus Smiles Dental"
    lead_provider: str = "Dr. Mahima Gupta"
    trainee_name: str = "Front Desk Trainee"
    patient_name: str = "Dental Patient"
    call_duration_seconds: Optional[int] = None


class EvaluatedScores(BaseModel):
    rapport_professionalism: int = Field(ge=0, le=10)
    discovery_needs_analysis: int = Field(ge=0, le=10)
    dental_sop_adherence: int = Field(ge=0, le=10)
    communication_skills: int = Field(ge=0, le=10)
    objection_handling: int = Field(ge=0, le=10)
    recommendation_quality: int = Field(ge=0, le=10)
    compliance_ethical_conduct: int = Field(ge=0, le=10)
    closing_effectiveness: int = Field(ge=0, le=10)
    clinic_protocol_adherence: int = Field(ge=0, le=10)

    overall_score: int = Field(ge=0, le=100, description="Programmatically computed weighted composite score")
    readiness_assessment: ReadinessTier = Field(description="Deterministic readiness tier")
    clamping_applied: bool = Field(default=False, description="Whether rule-based penalty clamping was triggered")


class QualitativeAnalysis(BaseModel):
    call_summary: str
    dental_sop_verbiage_audits: List[DentalSOPAuditItem] = Field(default_factory=list)
    clinic_protocol_audits: List[ClinicProtocolAuditItem] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    improvement_opportunities: List[str] = Field(default_factory=list)
    missed_opportunities: List[str] = Field(default_factory=list)
    compliance_review_security: ComplianceSecurityReview
    coaching_recommendations: List[str] = Field(default_factory=list)
    assessment_reasoning_justification: str
    dimension_explanations: Dict[str, str] = Field(
        default_factory=dict,
        description="Dynamic LLM-generated evidence and reasoning for each scorecard dimension",
    )


class DentalQAReportCard(BaseModel):
    call_metadata: CallMetadata
    scores: EvaluatedScores
    detailed_analysis: QualitativeAnalysis
    token_usage: Optional[Dict[str, Any]] = None

