"""
Dental QA Engine Module
Production-ready, deterministic 2-Stage Multi-Call evaluation engine for Dental Front Desk calls.
"""

from .service import DentalQAService, get_dental_qa_service
from .models import DentalCallEvaluation
from .core.orchestrator import evaluate_dental_call
from .core.stage3_scoring_engine import calculate_clamped_scores, DEFAULT_WEIGHTS
from .schemas import (
    DentalQAReportCard,
    CallMetadata,
    EvaluatedScores,
    QualitativeAnalysis,
    DentalSOPAuditResponse,
    ClinicProtocolAuditResponse,
    BehavioralEvaluationResponse,
)

__all__ = [
    "DentalQAService",
    "get_dental_qa_service",
    "DentalCallEvaluation",
    "evaluate_dental_call",
    "calculate_clamped_scores",
    "DEFAULT_WEIGHTS",
    "DentalQAReportCard",
    "CallMetadata",
    "EvaluatedScores",
    "QualitativeAnalysis",
    "DentalSOPAuditResponse",
    "ClinicProtocolAuditResponse",
    "BehavioralEvaluationResponse",
]
