"""USV Cardiometabolic Doctor Detailing QA evaluation prompt and structured Gemini JSON schema."""

USV_DOCTOR_EVALUATION_PROMPT = """You are an expert Pharmaceutical Medical Representative Quality Analyst and Scientific Detailing Coach for USV's Cardiometabolic Division.
Your task is to evaluate the cold detailing call between a Medical Sales Representative and an AI Physician.
Evaluate the Medical Sales Representative ONLY. Do NOT evaluate the AI Physician.
Use the entire conversation transcript and physician context as evidence. Be objective, strict, and specific, citing concrete behaviors or quotes from the transcript.
Do not invent information that was not present in the conversation.

Evaluate based on the following 8 criteria (each scored 1 to 10):
1. Rapport & Professionalism — Respectful, concise opening; acknowledged the physician's busy clinic schedule; gained permission before pitching; maintained poised scientific tone.
2. Discovery & Needs Analysis — Probed the physician's patient profile, current standard-of-care regimens, and clinical pain points (e.g., adherence, tolerability, affordability, renal/CV risk) before launching into product claims.
3. Product Knowledge & Scientific Accuracy — Accurately communicated molecule composition, approved indication, mechanism of action, dosing, and clinical trial evidence without exaggeration or unapproved claims.
4. Communication Skills — Clear, structured, conversational scientific communication; avoided empty marketing buzzwords ("breakthrough", "best-in-class") and addressed the physician's questions directly.
5. Objection Handling — Handled physician skepticism, switching inertia, efficacy demands, or affordability pushback calmly with relevant clinical rationale and honest boundaries.
6. Recommendation Quality — Tailored patient-type positioning appropriately to the physician's specialty, standard of care, and clinical constraints.
7. Compliance, Fair Balance & UCPMP 2024 —
   - FAIR BALANCE: Did the representative honestly acknowledge relevant side effects, contraindications, or monitoring requirements when discussing or asked about the product (instead of claiming "no side effects")?
   - UCPMP 2024 COMPLIANCE: Flag immediately in `compliance_issues` and penalize `compliance` (score 1-3) if the representative: (a) promoted off-label / unapproved indications, (b) offered gifts, cash, hospitality, travel, or conference sponsorships as inducements for prescriptions, (c) disparaged competitor companies/brands, or (d) dismissed a patient adverse event mentioned by the doctor instead of acknowledging it for pharmacovigilance reporting.
8. Closing Effectiveness — Summarized the key clinical takeaway, asked for an appropriate next step (e.g., trial in eligible patients, sharing approved literature), and closed courteously within time limits.

Note on Multilingual Calls: The call may be in Indian English, Hindi, or natural Hinglish. Understand all languages accurately and write the entire structured evaluation report in clear English.
"""

USV_DOCTOR_QA_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "scenario_practiced": {
            "type": "STRING",
            "description": "Brief summary of the physician persona, specialty, and detailing discussion",
        },
        "overall_score": {
            "type": "INTEGER",
            "description": "Overall score from 1 to 100 reflecting composite performance across all 8 criteria",
        },
        "rapport": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "discovery": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "product_knowledge": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "communication": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "objection_handling": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "recommendation_quality": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "compliance": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation covering fair balance and UCPMP 2024"},
            },
            "required": ["score", "reason"],
        },
        "closing": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evidence-based explanation for the score"},
            },
            "required": ["score", "reason"],
        },
        "positives": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Strongest detailing behaviors observed (empty list if none)",
        },
        "improvement_areas": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Key weaknesses and areas needing improvement",
        },
        "missed_opportunities": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Important probing questions, clinical evidence, or fair-balance disclosures missed",
        },
        "compliance_issues": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Fair-balance omissions, off-label claims, UCPMP 2024 breaches, or unhandled adverse events (empty list if none)",
        },
        "coaching_recommendations": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "3 specific actionable coaching recommendations for the representative",
        },
        "readiness_assessment": {
            "type": "STRING",
            "description": "Must be one of: 'Not Ready', 'Needs Significant Coaching', 'Developing', 'Ready With Supervision', 'Production Ready'",
        },
        "readiness_reasoning": {
            "type": "STRING",
            "description": "Detailed reasoning justifying the readiness assessment",
        },
    },
    "required": [
        "scenario_practiced",
        "overall_score",
        "rapport",
        "discovery",
        "product_knowledge",
        "communication",
        "objection_handling",
        "recommendation_quality",
        "compliance",
        "closing",
        "positives",
        "improvement_areas",
        "missed_opportunities",
        "compliance_issues",
        "coaching_recommendations",
        "readiness_assessment",
        "readiness_reasoning",
    ],
}
