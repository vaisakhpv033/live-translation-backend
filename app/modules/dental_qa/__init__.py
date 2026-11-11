"""
Dental QA Engine Module
Production-ready, deterministic 2-Stage Multi-Call evaluation engine for Dental Front Desk calls.
"""

from .service import DentalQAService, get_dental_qa_service
from .models import DentalCallEvaluation
from .core.orchestrator import evaluate_dental_call
from .core.stage3_scoring_engine import calculate_clamped_scores, DEFAULT_WEIGHTS
from .core.stage4_action_verifier import verify_appointment_action
from .schemas import (
    DentalQAReportCard,
    CallMetadata,
    EvaluatedScores,
    QualitativeAnalysis,
    DentalSOPAuditResponse,
    ClinicProtocolAuditResponse,
    BehavioralEvaluationResponse,
    SuggestedSlot,
    TranscriptOutcome,
    SlotAvailabilityResult,
    AppointmentActionVerdict,
)

__all__ = [
    "DentalQAService",
    "get_dental_qa_service",
    "DentalCallEvaluation",
    "evaluate_dental_call",
    "calculate_clamped_scores",
    "DEFAULT_WEIGHTS",
    "verify_appointment_action",
    "DentalQAReportCard",
    "CallMetadata",
    "EvaluatedScores",
    "QualitativeAnalysis",
    "DentalSOPAuditResponse",
    "ClinicProtocolAuditResponse",
    "BehavioralEvaluationResponse",
    "SuggestedSlot",
    "TranscriptOutcome",
    "SlotAvailabilityResult",
    "AppointmentActionVerdict",
]
