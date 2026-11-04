"""
SQLAlchemy Model for Dental Call QA Evaluations.
Stores granular 2-stage multi-call audit tables, 9 dimension scores,
clamping verdicts, and token cost tracking metrics.
"""

from sqlalchemy import Column, String, Integer, Text, Boolean, Float
from app.core.database import Base


class DentalCallEvaluation(Base):
    """
    Dedicated relational model for AutoCoach Dental Simulation Call QA Evaluations.
    Provides structured indexing for clinical compliance audits, SOP adherence,
    and trainee readiness metrics.
    """
    __tablename__ = "dental_evaluations"

    id = Column(String, primary_key=True, index=True)
    job_id = Column(String, index=True, nullable=False)
    overall_score = Column(Integer, nullable=False, default=0)
    clamping_applied = Column(Boolean, default=False)
    readiness_assessment = Column(String(50), nullable=True)

    # 9 Dimension Scores (1-10)
    rapport_score = Column(Integer, nullable=True)
    discovery_score = Column(Integer, nullable=True)
    dental_sop_score = Column(Integer, nullable=True)
    clinic_protocol_score = Column(Integer, nullable=True)
    communication_score = Column(Integer, nullable=True)
    objection_handling_score = Column(Integer, nullable=True)
    recommendation_quality_score = Column(Integer, nullable=True)
    compliance_score = Column(Integer, nullable=True)
    closing_score = Column(Integer, nullable=True)

    # Granular Audit Tables & Qualitative Records (Serialized JSON)
    call_summary = Column(Text, nullable=True)
    sop_audit_table = Column(Text, nullable=True)
    clinic_audit_table = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)
    improvement_opportunities = Column(Text, nullable=True)
    missed_opportunities = Column(Text, nullable=True)
    coaching_recommendations = Column(Text, nullable=True)
    compliance_review_security = Column(Text, nullable=True)
    assessment_reasoning_justification = Column(Text, nullable=True)

    # Gemini Token Accounting & Cost Tracking
    total_prompt_tokens = Column(Integer, nullable=True, default=0)
    total_candidates_tokens = Column(Integer, nullable=True, default=0)
    total_thoughts_tokens = Column(Integer, nullable=True, default=0)
    estimated_cost_usd = Column(Float, nullable=True, default=0.0)

    created_at = Column(String, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DentalCallEvaluation(job_id={self.job_id}, "
            f"overall_score={self.overall_score}, "
            f"readiness={self.readiness_assessment}, "
            f"clamped={self.clamping_applied})>"
        )

