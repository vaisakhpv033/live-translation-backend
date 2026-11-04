"""
Stage 3: Deterministic Clamping & Scoring Engine
Pure Python calculation: Zero LLM hallucinations, resilient business clamps, and exact weighted composite scores.
"""

from typing import Dict, Any, List
from app.modules.dental_qa.schemas import (
    DentalSOPAuditItem,
    ClinicProtocolAuditItem,
    EvaluatedScores,
)

DEFAULT_WEIGHTS = {
    "dental_sop_adherence": 0.20,
    "objection_handling": 0.15,
    "rapport_professionalism": 0.10,
    "discovery_needs_analysis": 0.10,
    "communication_skills": 0.10,
    "recommendation_quality": 0.10,
    "compliance_ethical_conduct": 0.10,
    "clinic_protocol_adherence": 0.10,
    "closing_effectiveness": 0.05,
}

TIER_1_CLINIC_RULE_IDS = {
    "citrus_10_f_hours",
    "citrus_5_b_prepayment",
    "citrus_3_a_insurance",
    "citrus_6_b_cancellation",
}


def is_closed_day_violation(c: ClinicProtocolAuditItem) -> bool:
    r_id = (c.rule_id or "").strip().lower()
    r_title = (c.rule_title or "").strip().lower()
    return "citrus_10_f_hours" in r_id or "operating days" in r_title or "hours" in r_id


def is_prepayment_violation(c: ClinicProtocolAuditItem) -> bool:
    r_id = (c.rule_id or "").strip().lower()
    r_title = (c.rule_title or "").strip().lower()
    return "citrus_5_b_prepayment" in r_id or "prepayment" in r_title or "credit card" in r_title


def is_tier_1_violation(c: ClinicProtocolAuditItem) -> bool:
    r_id = (c.rule_id or "").strip().lower()
    return any(t1_id in r_id for t1_id in TIER_1_CLINIC_RULE_IDS)


def calculate_clamped_scores(
    raw_scores: Dict[str, int],
    sop_audits: List[DentalSOPAuditItem],
    clinic_audits: List[ClinicProtocolAuditItem],
    weights: Dict[str, float] = DEFAULT_WEIGHTS,
) -> EvaluatedScores:
    """
    Enforces deterministic clamps and calculates the exact weighted composite overall score.
    """
    clamped = dict(raw_scores)

    # 1. Analyze Audit Tables for Critical Violations (case-insensitive)
    clinic_violations = [c for c in clinic_audits if (c.verdict or "").strip().lower() == "violated"]
    sop_violations = [s for s in sop_audits if (s.verdict or "").strip().lower() == "violated"]
    sop_misses = [s for s in sop_audits if (s.verdict or "").strip().lower() == "missed opportunity"]

    # 2. Hard Clamps: Clinic Operating Rules
    has_closed_day_violation = any(is_closed_day_violation(c) for c in clinic_violations)
    has_prepayment_violation = any(is_prepayment_violation(c) for c in clinic_violations)
    has_any_tier_1_violation = any(is_tier_1_violation(c) for c in clinic_violations)

    penalty_rule_triggered = (
        has_closed_day_violation
        or has_prepayment_violation
        or has_any_tier_1_violation
        or len(sop_violations) >= 1
    )

    if has_closed_day_violation or has_prepayment_violation:
        clamped["clinic_protocol_adherence"] = min(clamped.get("clinic_protocol_adherence", 10), 3)
        clamped["compliance_ethical_conduct"] = min(clamped.get("compliance_ethical_conduct", 10), 4)
    elif has_any_tier_1_violation:
        clamped["clinic_protocol_adherence"] = min(clamped.get("clinic_protocol_adherence", 10), 4)
        clamped["compliance_ethical_conduct"] = min(clamped.get("compliance_ethical_conduct", 10), 5)
    elif len(clinic_violations) >= 1:
        clamped["clinic_protocol_adherence"] = min(clamped.get("clinic_protocol_adherence", 10), 5)

    # 3. Hard Clamps: Dental SOP Adherence
    if len(sop_violations) >= 2:
        clamped["dental_sop_adherence"] = min(clamped.get("dental_sop_adherence", 10), 4)
        clamped["objection_handling"] = min(clamped.get("objection_handling", 10), 5)
    elif len(sop_violations) == 1:
        clamped["dental_sop_adherence"] = min(clamped.get("dental_sop_adherence", 10), 6)
        clamped["objection_handling"] = min(clamped.get("objection_handling", 10), 7)
    elif len(sop_misses) >= 2:
        clamped["dental_sop_adherence"] = min(clamped.get("dental_sop_adherence", 10), 7)

    # 4. Programmatic Weighted Sum
    total_composite = 0.0
    for metric, weight in weights.items():
        score_val = clamped.get(metric, 5)
        # Bounded between 1 and 10
        score_val = max(1, min(10, score_val))
        total_composite += (score_val * 10.0) * weight

    overall_score = int(round(total_composite))
    overall_score = max(1, min(100, overall_score))

    # 5. Deterministic Readiness Tier
    has_critical_fail = (
        has_closed_day_violation
        or has_prepayment_violation
        or has_any_tier_1_violation
        or len(clinic_violations) >= 2
        or len(sop_violations) >= 2
    )

    if overall_score >= 90 and not has_critical_fail:
        readiness = "Production Ready"
    elif overall_score >= 80 and not has_critical_fail:
        readiness = "Ready With Supervision"
    elif overall_score >= 65:
        readiness = "Developing"
    elif overall_score >= 50:
        readiness = "Needs Significant Coaching"
    else:
        readiness = "Not Ready"

    # Clamping is considered active if penalties were triggered OR if raw scores were clamped downward
    clamping_applied = penalty_rule_triggered or (clamped != raw_scores)

    return EvaluatedScores(
        rapport_professionalism=clamped["rapport_professionalism"],
        discovery_needs_analysis=clamped["discovery_needs_analysis"],
        dental_sop_adherence=clamped["dental_sop_adherence"],
        communication_skills=clamped["communication_skills"],
        objection_handling=clamped["objection_handling"],
        recommendation_quality=clamped["recommendation_quality"],
        compliance_ethical_conduct=clamped["compliance_ethical_conduct"],
        closing_effectiveness=clamped["closing_effectiveness"],
        clinic_protocol_adherence=clamped["clinic_protocol_adherence"],
        overall_score=overall_score,
        readiness_assessment=readiness,
        clamping_applied=clamping_applied,
    )

