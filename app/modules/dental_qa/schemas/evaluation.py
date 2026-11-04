"""
Pydantic Schemas for Stage 2 Holistic Behavioral Evaluator
Grades the remaining 7 behavioral dimensions and synthesizes qualitative coaching sections.
"""

from typing import List, Dict
from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    score: int = Field(ge=1, le=10, description="Score from 1 to 10")
    reason: str = Field(description="Evidence-based reasoning for the assigned score")


class ComplianceSecurityReview(BaseModel):
    pci_dss_prepayment: str = Field(description="Evaluation of credit card / prepayment collection handling")
    hipaa_privacy: str = Field(description="Evaluation of HIPAA compliance and medical privacy")
    security_credentials: str = Field(description="Audit confirming zero internal passwords, TIN/NPI, or manager numbers recited")


class BehavioralEvaluationResponse(BaseModel):
    # 7 Core Behavioral Dimensions (1-10)
    rapport_professionalism: DimensionScore = Field(description="Warmth, greeting, and empathy")
    discovery_needs_analysis: DimensionScore = Field(description="Diagnostic questioning and triage")
    communication_skills: DimensionScore = Field(description="Clarity, conversational pacing, and jargon avoidance")
    objection_handling: DimensionScore = Field(description="Handling cost, schedule, or provider hesitation")
    recommendation_quality: DimensionScore = Field(description="Appropriate appointment selection and expectations")
    compliance_ethical_conduct: DimensionScore = Field(description="Ethical conduct, no unauthorized diagnoses or payout guarantees")
    closing_effectiveness: DimensionScore = Field(description="Appointment recap, directions, and sign-off")

    # Qualitative Detail Sections
    call_summary: str = Field(description="Executive 2-3 sentence overview of the call and trainee handling")
    strengths: List[str] = Field(default_factory=list, description="Top positive behaviors observed")
    improvement_opportunities: List[str] = Field(default_factory=list, description="Key developmental areas needing correction")
    missed_opportunities: List[str] = Field(default_factory=list, description="Unused promotions, missed questions, or verbiages")
    compliance_review_security: ComplianceSecurityReview = Field(description="Specific compliance and security audit checks")
    coaching_recommendations: List[str] = Field(default_factory=list, description="Actionable training drills and practice exercises")
    assessment_reasoning_justification: str = Field(description="Detailed coaching narrative explaining the overall evaluation")

