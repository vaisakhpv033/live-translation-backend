import json
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import httpx
from app.core.config import get_settings
from app.services.sop_playbook import DENTAL_SOP_PLAYBOOK_PROMPT_TEXT

logger = logging.getLogger("translation-agent-backend.services.evaluation_service")
settings = get_settings()

# ──────────────────────────────────────────────────────────────
#  Gemini QA Report Card Schema (structured JSON output)
# ──────────────────────────────────────────────────────────────

GEMINI_QA_REPORT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "scenario_practiced": {
            "type": "STRING",
            "description": "Brief summary of customer profile and situation"
        },
        "overall_score": {
            "type": "INTEGER",
            "description": "Overall score from 1 to 100"
        },
        "rapport": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "discovery": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "product_knowledge": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "communication": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "objection_handling": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "recommendation_quality": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "compliance": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "closing": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "positives": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of strongest behaviors observed (empty list if none)"
        },
        "improvement_areas": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of the most important weaknesses/improvements"
        },
        "missed_opportunities": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of important questions that should have been asked"
        },
        "compliance_issues": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of compliance concerns/violations (empty list if none)"
        },
        "coaching_recommendations": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "3 specific coaching recommendations"
        },
        "readiness_assessment": {
            "type": "STRING",
            "description": "Readiness assessment (must be one of: 'Not Ready', 'Needs Significant Coaching', 'Developing', 'Ready With Supervision', 'Production Ready')"
        },
        "readiness_reasoning": {
            "type": "STRING",
            "description": "Detailed reasoning for the readiness assessment"
        },
        "claim_summary": {
            "type": "OBJECT",
            "description": "Structured 13-field claim intake summary for motor claim calls. If any field is not available, return 'N/A'.",
            "properties": {
                "claim_number": {"type": "STRING", "description": "Official claim number e.g. MCL-26-118492 or 'N/A'"},
                "policy": {"type": "STRING", "description": "Policy number and identity verification status e.g. 'SGI/MOT/2026/448127, identity verified' or 'N/A'"},
                "insured_and_vehicle": {"type": "STRING", "description": "Insured person and vehicle model/reg e.g. 'Suresh Kumar; Hyundai Creta, MH 12 AB 4521' or 'N/A'"},
                "when_and_where": {"type": "STRING", "description": "Incident timing and location from conversation e.g. 'About 20 minutes before the call, Baner Road signal, Pune' or 'N/A'"},
                "what_happened": {"type": "STRING", "description": "Collision summary from conversation e.g. 'Hit from behind by a tempo while stopped at a signal' or 'N/A'"},
                "damage_reported": {"type": "STRING", "description": "Vehicle damages reported from conversation e.g. 'Rear bumper, tail light, boot lid' or 'N/A'"},
                "third_party": {"type": "STRING", "description": "Third party vehicle and injury details from conversation e.g. 'Tempo MH 14 GH 2290; a bike rider with a minor hand injury' or 'N/A'"},
                "police_report": {"type": "STRING", "description": "Police report advice status from conversation e.g. 'Advised, as a third party was injured' or 'N/A'"},
                "garage_and_tow": {"type": "STRING", "description": "Chosen garage and towing from conversation e.g. 'Baner Motors (cashless), towed under roadside assistance' or 'N/A'"},
                "documents_requested": {"type": "STRING", "description": "Documents requested from customer e.g. 'Claim form, RC, driving licence, police report, photos' or 'N/A'"},
                "next_step": {"type": "STRING", "description": "Next steps promised e.g. 'Surveyor to call within 24 hours; WhatsApp summary sent' or 'N/A'"},
                "compliance": {"type": "STRING", "description": "Compliance status synthesized from telemetry and dialogue e.g. 'Recording disclosed; two alerts raised and corrected on the call' or 'N/A'"},
                "customer_mood": {"type": "STRING", "description": "Customer mood trajectory synthesized from telemetry and dialogue e.g. 'Anxious mid-call, positive at the close' or 'N/A'"}
            },
            "required": [
                "claim_number",
                "policy",
                "insured_and_vehicle",
                "when_and_where",
                "what_happened",
                "damage_reported",
                "third_party",
                "police_report",
                "garage_and_tow",
                "documents_requested",
                "next_step",
                "compliance",
                "customer_mood"
            ]
        }
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
        "claim_summary"
    ]
}

# ──────────────────────────────────────────────────────────────
#  Gemini Dental QA Report Card Schema (AutoCoach SOP Adherence)
# ──────────────────────────────────────────────────────────────

GEMINI_DENTAL_QA_REPORT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "scenario_practiced": {
            "type": "STRING",
            "description": "Brief summary of patient profile, dental concerns, and practice context"
        },
        "overall_score": {
            "type": "INTEGER",
            "description": "Overall score from 1 to 100 based on rubric category weights"
        },
        "rapport": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "discovery": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "sop_adherence": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Evaluation of adherence to standard dental front-desk objection verbiages and protocols"}
            },
            "required": ["score", "reason"]
        },
        "communication": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "objection_handling": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "recommendation_quality": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "compliance": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "closing": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "positives": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of strongest behaviors observed (empty list if none)"
        },
        "improvement_areas": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of the most important weaknesses/improvements"
        },
        "missed_opportunities": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of important questions or verbiages that should have been used"
        },
        "compliance_issues": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of compliance concerns/violations (empty list if none)"
        },
        "coaching_recommendations": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "3 specific coaching recommendations"
        },
        "readiness_assessment": {
            "type": "STRING",
            "description": "Readiness assessment (must be one of: 'Not Ready', 'Needs Significant Coaching', 'Developing', 'Ready With Supervision', 'Production Ready')"
        },
        "readiness_reasoning": {
            "type": "STRING",
            "description": "Detailed reasoning for the readiness assessment"
        },
        "sop_adherence_summary": {
            "type": "OBJECT",
            "description": "Structured evaluation of the trainee's adherence to official Dental Front Desk SOPs and objection verbiages. Use 'N/A' if the scenario was not encountered.",
            "properties": {
                "system_down_handling": {"type": "STRING", "description": "Did the trainee buy time politely and offer tentative date + callback if system froze? e.g. 'Adhered', 'Violated: hung up', or 'N/A'"},
                "spanish_patient_handling": {"type": "STRING", "description": "Did trainee apologize politely in Spanish/English and offer transfer or callback with Spanish speaker? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "doctor_request_handling": {"type": "STRING", "description": "Did trainee avoid putting caller on hold to search for doctor, state dr is with patient, and offer to take message/callback? e.g. 'Adhered', 'Violated: put on hold', or 'N/A'"},
                "note_taking_pause_handling": {"type": "STRING", "description": "Did trainee politely request a moment to note details for the clinical team to avoid awkward silence? e.g. 'Adhered', 'Violated: silence', or 'N/A'"},
                "patient_moving_handling": {"type": "STRING", "description": "Did trainee warmly express regret, wish luck on move, and leave door open to return? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "billing_dept_handling": {"type": "STRING", "description": "Did trainee take information and promise billing callback within 2 business days (or escalate)? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "remote_inquiry_handling": {"type": "STRING", "description": "Did trainee explain remote role positively as freeing in-office team to focus on patient care? e.g. 'Adhered', 'Violated: evasive', or 'N/A'"},
                "repeat_offender_handling": {"type": "STRING", "description": "Did trainee state schedule is booked out and advise calling day-of for same-day openings? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "archived_inactive_patient_handling": {"type": "STRING", "description": "Did trainee check for emergency, and if general exam use booked-out / insurance referral verbiage? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "balance_due_handling": {"type": "STRING", "description": "Did trainee courteously inform and collect pending balance before booking per protocol? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "xray_transfer_handling": {"type": "STRING", "description": "Did trainee explain 6-month validity rule, 48-hr email requirement, and condition check? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "first_visit_explanation": {"type": "STRING", "description": "Did trainee explain exam + X-ray workflow and build warmth about the doctor/practice? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "urgent_emergency_triage": {"type": "STRING", "description": "Did trainee assess urgency (pain/swelling/trauma) and offer same-day priority slot if emergency? e.g. 'Adhered', 'Violated', or 'N/A'"},
                "overall_sop_verdict": {"type": "STRING", "description": "'Fully Compliant', 'Partially Compliant', or 'Non-Compliant' with dental front desk SOPs"}
            },
            "required": [
                "system_down_handling",
                "spanish_patient_handling",
                "doctor_request_handling",
                "note_taking_pause_handling",
                "patient_moving_handling",
                "billing_dept_handling",
                "remote_inquiry_handling",
                "repeat_offender_handling",
                "archived_inactive_patient_handling",
                "balance_due_handling",
                "xray_transfer_handling",
                "first_visit_explanation",
                "urgent_emergency_triage",
                "overall_sop_verdict"
            ]
        },
        "sop_audit_table": {
            "type": "ARRAY",
            "description": "Dynamic line-by-line audit of each specific SOP trigger, objection, or clinical scenario that occurred on this call. Empty list if no specific SOP objection was triggered.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "sop_id": {"type": "STRING", "description": "Identifier of the SOP rule from the playbook (e.g. 'sop_external_xrays', 'sop_prepayment_rebuttal')"},
                    "sop_title": {"type": "STRING", "description": "Title of the SOP rule"},
                    "section": {"type": "STRING", "description": "SOP section category e.g. 'Reason of Appointment', 'Insurance & Fees', 'collect payment', 'select office'"},
                    "patient_trigger_quote": {"type": "STRING", "description": "Direct verbatim quote from transcript of the patient's objection, inquiry, or challenge"},
                    "trainee_actual_quote": {"type": "STRING", "description": "Direct verbatim quote of the trainee's actual spoken response"},
                    "verdict": {
                        "type": "STRING",
                        "description": "Compliance verdict: 'Adhered', 'Partially Adhered', 'Violated', or 'Missed Opportunity'"
                    },
                    "violation_details": {"type": "STRING", "description": "Specific explanation of what was violated or missing from the required protocol, or praise if adhered"},
                    "approved_sop_verbiage": {"type": "STRING", "description": "Official approved verbiage and directives from the SOP Playbook"}
                },
                "required": [
                    "sop_id",
                    "sop_title",
                    "section",
                    "patient_trigger_quote",
                    "trainee_actual_quote",
                    "verdict",
                    "violation_details",
                    "approved_sop_verbiage"
                ]
            }
        }
    },
    "required": [
        "scenario_practiced",
        "overall_score",
        "rapport",
        "discovery",
        "sop_adherence",
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
        "sop_adherence_summary",
        "sop_audit_table"
    ]
}

# ──────────────────────────────────────────────────────────────
#  Scenario-Specific System Prompts
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT_SBI = """You are an expert SBI Mutual Fund sales trainer and quality analyst.
Your task is to evaluate the conversation between a sales representative and a prospective customer.
Evaluate the sales representative only. Do not evaluate the customer.
Use the entire conversation transcript as evidence. Be objective and specific.
Do not invent information that was not present in the conversation.

Evaluate based on the following criteria:
1. Rapport & Professionalism
2. Discovery & Needs Analysis
3. Product Knowledge
4. Communication Skills
5. Objection Handling
6. Recommendation Quality
7. Compliance & Ethical Conduct
8. Closing Effectiveness"""

SYSTEM_PROMPT_WTW = """You are an expert Willis Towers Watson (WTW) benefits helpdesk quality analyst.
Your task is to evaluate the conversation between a benefits helpdesk analyst and an employee caller.
Evaluate the helpdesk analyst ONLY. Do not evaluate the caller.
Use the entire conversation transcript as evidence. Be objective and specific.
Do not invent information that was not present in the conversation.

This is a WTW corporate benefits helpdesk call. The caller is an employee asking about a denied insurance claim and plan options.

Evaluate based on the following criteria (mapped to the scoring categories):

1. Rapport & Professionalism — Was the analyst professional, empathetic, and courteous?
2. Discovery & Verification — Did the analyst properly verify the caller's identity WITHOUT reading back sensitive PII (SSN, DOB digits)? CRITICAL: If the analyst read back any SSN digits or full date of birth to the caller, this is a SEVERE compliance violation and must be scored 1-2.
3. Product Knowledge (Plan & Policy Accuracy) — Did the analyst accurately explain plan rules? CRITICAL: If the analyst stated that mid-year plan changes are allowed without mentioning Qualifying Life Events (QLE) or Open Enrollment periods, this is an ACCURACY ERROR and must be scored 1-3.
4. Communication Skills — Did the analyst explain out-of-network vs in-network coverage clearly and in plain language?
5. Objection Handling (Caller Frustration Management) — How well did the analyst handle the caller's frustration about the denied claim?
6. Recommendation Quality (Guidance & Next Steps) — Did the analyst provide actionable next steps (appeal process, finding in-network providers, etc.)?
7. Compliance & Privacy Guardrails — Overall compliance assessment. ANY PII exposure (reading back SSN/DOB digits) is an automatic critical failure. Any inaccurate eligibility statements are compliance violations.
8. Closing Effectiveness — Did the analyst summarize the resolution, confirm next steps, and close the call professionally?

PAY SPECIAL ATTENTION TO THESE TWO PLANTED SCENARIOS:
- PII EXPOSURE: If the analyst reads back, confirms, or repeats any digits of the caller's SSN or date of birth, flag this as a CRITICAL compliance violation in compliance_issues and score Discovery/Verification and Compliance categories severely (1-2 out of 10).
- ELIGIBILITY ACCURACY: If the analyst says the caller can switch plans mid-year without mentioning QLE or Open Enrollment, flag this as an ACCURACY ERROR in compliance_issues and score Product Knowledge severely (1-3 out of 10).

If the analyst correctly refuses to read back PII and correctly states that mid-year changes require a QLE, acknowledge these as strong compliance behaviors in positives."""

SYSTEM_PROMPT_LIVE_CALL = """You are an expert health insurance quality analyst and sales coach.
Your task is to evaluate the conversation between a health insurance representative and a customer.
Evaluate the representative ONLY. Do not evaluate the customer.
Use the entire conversation transcript as evidence. Be objective and specific.
Do not invent information that was not present in the conversation.

Evaluate based on the following criteria (mapped to the scoring categories):
1. Rapport & Professionalism — Did the representative show empathy, professional greeting, and tone?
2. Discovery & Needs Analysis — Did the representative ask questions to understand the customer's medical history, current coverage, and specific healthcare needs?
3. Product Knowledge — Did the representative explain health insurance policies, deductibles, copayments, and in-network vs out-of-network coverage accurately?
4. Communication Skills — Was the explanation of complex health insurance terms clear and easy to understand?
5. Objection Handling — How well did the representative address concerns about premium costs, coverage exclusions, or denied claims?
6. Recommendation Quality — Did the representative suggest appropriate plans based on the customer's budget and medical requirements?
7. Compliance & Privacy Guardrails — Did the representative adhere to HIPAA or local regulations, ensuring customer details and PII (like full date of birth, SSN, or clinical history) are handled securely without reading back sensitive information unprompted?
8. Closing Effectiveness — Did the representative summarize next steps, confirm understanding, and close the call professionally?"""

SYSTEM_PROMPT_TWO_BROTHERS = """You are an expert Two Brothers Organic Farms (TBOF) customer experience quality analyst and call center coach.
Your task is to evaluate the conversation between a Two Brothers Organic Farms customer support representative and a customer.
Evaluate the representative ONLY. Do not evaluate the customer.
Use the entire conversation transcript as evidence. Be objective, strict, and specific.
Do not invent information that was not present in the conversation.

This is a Two Brothers Organic Farms live support call. The caller may be inquiring about an order status/delay, farm product details (e.g. A2 Cultured Desi Ghee, Organic Heirloom Kapli Atta), nutrition/dietary inquiries, or purchasing new farm products.

Evaluate based on the following criteria (mapped to the scoring categories):

1. Rapport & Professionalism — Did the representative offer a warm, polite opening greeting (e.g., "Namaste! Thank you for calling Two Brothers Organic Farms...")? Did they maintain an empathetic, calm, respectful, and attentive tone throughout the call?
2. Discovery & Verification — Did the representative properly verify the customer's registered mobile number / identity before sharing order details? Did they clarify whether the customer needed order tracking, product guidance, or checkout support?
3. Product Knowledge (Farm & Nutrition Accuracy) — Did the representative explain Two Brothers Organic Farms products accurately without making medical cure claims?
   - A2 Cultured Desi Ghee: Made from indigenous Gir cow whole milk curd using traditional two-way wooden Bilona churning (not industrial cream), certified Glyphosate-Free, rich in butyric acid and fat-soluble vitamins (A, D, E, K), virtually lactose-free.
   - Organic Heirloom Kapli Atta (Emmer Wheat): Ancient heirloom wheat, low Glycemic Index (Low GI - slow glucose breakdown, avoids sugar spikes), rich in fiber & nutrients, naturally fragile gluten (easier on gut digestion, but NOT for severe celiac disease).
4. Communication Skills — Was the explanation of logistics delays, order tracking, or nutritional concepts clear, structured, and easy to understand? Did the representative avoid robotic jargon and adapt smoothly to the customer's language and tone?
5. Objection Handling (Delayed Delivery & Customer Frustration) — How effectively did the representative handle concerns regarding delayed shipments? Did they explain the root cause transparently (e.g., transit congestion / sorting hub weather delays via Blue Dart/ClickPost) without making excuses or becoming defensive? Did they provide a realistic revised delivery date (ETA) and reassure package integrity?
6. Recommendation Quality (Advisory & Checkout Assistance) — Did the representative provide helpful dietary/usage suggestions (e.g. Kapli Atta for low GI diet, A2 Ghee for gut wellness)? When purchase interest was shown, did they offer or generate an instant checkout / WhatsApp booking link without being pushy or aggressive?
7. Compliance & Privacy Guardrails —
   - CRITICAL VIOLATION: If the representative asks for OTP, CVV, UPI PIN, password, or full debit/credit card numbers, flag this immediately as a CRITICAL compliance violation in compliance_issues and score Compliance severely (1-2 out of 10).
   - MEDICAL CLAIMS VIOLATION: If the representative claims products "cure" chronic medical diseases (e.g., curing diabetes, cancer, or hypertension), flag this as an ACCURACY/COMPLIANCE ERROR in compliance_issues and score Product Knowledge and Compliance severely (1-3 out of 10).
   - ACCURATE PROMISES: The representative must not invent fake tracking IDs or make unrealistic delivery promises not backed by courier logistics data.
8. Closing Effectiveness — Did the representative summarize the resolution and next steps (e.g., tracking updates via SMS, revised ETA, WhatsApp checkout link), confirm customer satisfaction, and close the call with warmth and traditional Indian hospitality (Namaste)?"""


SYSTEM_PROMPT_MOTOR_CLAIM = """You are an expert Motor Insurance Claims quality analyst and claims desk coach for Zurich Kotak General Insurance (Shield Claims).
Your task is to evaluate the conversation between a motor claims customer service representative (operating with a live Copilot) and a policyholder/caller reporting a vehicle accident.
Evaluate the representative ONLY. Do not evaluate the caller.
Use the entire conversation transcript as evidence. Be objective, strict, and specific.
Do not invent information that was not present in the conversation.

This is a motor accident claim intimation call. The caller (e.g. Mr. Suresh Kumar) is reporting an accident (e.g., Hyundai Creta MH 12 AB 4521 hit by a tempo or involved in a collision at Baner Road, Pune).

Evaluate based on the following criteria (mapped to the scoring categories):

1. Rapport & Professionalism —
   - Empathy and safety check FIRST: Did the representative immediately express empathy and verify passenger/caller physical safety and car pull-over status BEFORE demanding vehicle registration or policy numbers?
   - Professional recording disclosure: Was the call recording disclosure provided appropriately?
   - Did the representative maintain a calm, reassuring, empathetic tone throughout the call?

2. Discovery & Verification —
   - Did the representative request the vehicle registration number (e.g., MH 12 AB 4521) without repeating it excessively?
   - Once policy was located, did they properly verify the policyholder's identity (Mr. Suresh Kumar) and registered mobile number (ending 7714)?
   - Did they inquire about the incident location (e.g., Baner Road signal, Pune)?
   - Did they determine third-party involvement and capture third-party vehicle details (e.g., tempo/bike registration like MH 14 GH 2290)?

3. Product Knowledge (Policy & Coverage Accuracy) —
   - Zero Depreciation Cover: Did the representative accurately explain that Zero Depreciation covers 100% replacement of parts (fiberglass, rubber, nylon, plastic, metal) and labor without depreciation deductions?
   - Deductible Explanation: Did they accurately explain the statutory compulsory deductible of ₹1,000 under the policy?
   - Surveyor Inspection Role: Did the representative accurately explain that final claim approval and assessment rests with the insurance surveyor?

4. Communication Skills —
   - Did the representative communicate clearly, patiently, and without robotic jargon or interrogative grilling?
   - Dynamic bypass & listening: Did the representative listen carefully and avoid re-asking questions for information the caller had already volunteered (e.g. location, injury, damage)?

5. Objection Handling (Customer Anxiety & Distress Management) —
   - How effectively did the representative address the caller's anxiety about past bad claims experiences, repair bills, or unexpected costs?
   - Did they reassure the caller regarding transparent cashless settlement and smooth RSA assistance?

6. Recommendation Quality (Guidance, Towing & Safety Advice) —
   - Drivability Assessment & Warning: When vehicle damage (e.g., broken tail light, open/dented boot) was reported, did the representative clearly advise that driving with broken tail lights or an open boot is unsafe and illegal?
   - Cashless RSA Towing Offer: Did they offer free flatbed towing under Roadside Assistance (RSA) to the nearest authorized cashless workshop (Baner Motors, 2.1 km away or Pashan Auto Care)?
   - Document Guidance: Did they clearly outline the required documents (signed claim form, RC copy, driving licence, damage photos, police intimation report if injury occurred)?

7. Compliance & Regulatory Guardrails —
   - CRITICAL COMPLIANCE VIOLATION (PAYMENT PROMISE): The representative must NEVER promise, guarantee, or state that "100% of the claim will be paid" or "your claim will definitely be approved" before the surveyor inspects the car. If the representative makes unauthorized payment/approval guarantees, flag this as a CRITICAL violation in compliance_issues and score Compliance severely (1-2 out of 10).
   - CRITICAL COMPLIANCE VIOLATION (THIRD-PARTY FIR INJURY): If a third party (e.g. bike rider, pedestrian, or third-party passenger) suffered any bodily injury, the representative MUST advise filing an intimation or report at the nearest police station (FIR / GD). If the representative advises skipping or fails to advise a police report for injuries, flag this as a CRITICAL compliance violation in compliance_issues and score Compliance severely (1-2 out of 10).
   - FRAUD & PRIVACY: The representative must never ask for OTP, CVV, UPI PIN, or bank passwords.

8. Closing Effectiveness —
   - Did the representative provide the official Claim Intimation Reference Number (e.g., MCL-26-118492)?
   - Did they confirm that an insurance surveyor will reach out within 24 hours?
   - Did they confirm dispatching the WhatsApp summary containing garage location, towing details, and document upload links?
   - Did they close the call professionally and courteously?

CLAIM SUMMARY EXTRACTION DIRECTIVE:
You must also synthesize a structured "claim_summary" object containing the following 13 fields:
1. claim_number: Official claim number (from telemetry or dialogue e.g. "MCL-26-118492"). If not available, "N/A".
2. policy: Policy number and identity verification status (e.g. "SGI/MOT/2026/448127, identity verified"). If not available, "N/A".
3. insured_and_vehicle: Policyholder name and insured vehicle model & registration (e.g. "Suresh Kumar; Hyundai Creta, MH 12 AB 4521" or from telemetry/dialogue). If not available, "N/A".
4. when_and_where: Incident time and location from conversation (e.g. "About 20 minutes before the call, Baner Road signal, Pune"). Must be extracted from dialogue. If not available, "N/A".
5. what_happened: Brief description of collision from conversation (e.g. "Hit from behind by a tempo while stopped at a signal"). Must be extracted from dialogue. If not available, "N/A".
6. damage_reported: Vehicle damages reported by caller from conversation (e.g. "Rear bumper, tail light, boot lid"). If not available, "N/A".
7. third_party: Details of third-party vehicle and any injury mentioned from conversation (e.g. "Tempo MH 14 GH 2290; a bike rider with a minor hand injury"). If no third party, "None" or "N/A".
8. police_report: Police report/FIR status and advice from conversation (e.g. "Advised, as a third party was injured" or "Not required for single vehicle"). If not available, "N/A".
9. garage_and_tow: Chosen network garage and towing arrangement from conversation (e.g. "Baner Motors (cashless), towed under roadside assistance"). Must be extracted from dialogue. If not available, "N/A".
10. documents_requested: Checklist of documents requested from the customer from conversation (e.g. "Claim form, RC, driving licence, police report, photos"). If not available, "N/A".
11. next_step: Next actions promised to the customer from conversation (e.g. "Surveyor to call within 24 hours; WhatsApp summary sent"). If not available, "N/A".
12. compliance: Compliance disclosure and alerts summary synthesized from telemetry and dialogue (e.g. "Recording disclosed; two alerts raised and corrected on the call"). If not available, "N/A".
13. customer_mood: Customer mood trajectory across call synthesized from telemetry and conversation (e.g. "Anxious mid-call, positive at the close"). If not available, "N/A".

For any field where information is not present or cannot be determined from either the telemetry or transcript, return "N/A"."""


SYSTEM_PROMPT_DENTAL_COACH = f"""You are an expert Dental Front Desk Quality Analyst, Patient Experience Trainer, and Call Center Coach.
Your task is to evaluate the conversation between a Dental Front Desk Representative / Trainee and a dental patient (caller).
Evaluate the Front Desk Trainee ONLY. Do NOT evaluate the patient.
Use the entire conversation transcript as evidence. Be objective, thorough, and specific with direct quotes.
Do not invent information that was not present in the conversation.

EVALUATION CRITERIA (Scored 1 to 10 with direct evidence):
1. Rapport & Professionalism — Warm greeting, empathy, identifying self and dental practice, treating patient like family.
2. Discovery & Needs Analysis — Asking diagnostic questions regarding patient's dental pain, symptoms, dental history, and urgency.
3. SOP Adherence — Strict adherence to dental front desk verbiages and protocols (System down, Spanish patient, Doctor request, Note pauses, Balance collection, 6-month X-rays, Payment hold, etc.).
4. Communication Skills — Clear, empathetic, jargon-free explanations, conversational pacing, polite articulation.
5. Objection Handling — Managing pushback on pricing, past-due balances, doctor availability, appointment availability, or remote employee status without defensiveness.
6. Recommendation Quality — Scheduling appropriate appointment slots, explaining comprehensive exam/X-ray procedures (or 3D cone beam scan for implants), prioritizing emergency triage if in pain.
7. Compliance & Privacy Guardrails — HIPAA compliance, privacy, reminding patient that the doctor must examine before diagnosis, not making unauthorized medical diagnoses or guarantees.
8. Closing Effectiveness — Reconfirming appointment date/time, doctor name, parking/arrival instructions, callback numbers, warm sign-off.

{DENTAL_SOP_PLAYBOOK_PROMPT_TEXT}

REASONING & INTERNAL CONSISTENCY INSTRUCTIONS:
Use your internal reasoning process to analyze the transcript thoroughly before generating the structured report card:

1. CHRONOLOGICAL TRANSCRIPT WALKTHROUGH:
   Trace the dialogue turn by turn. Identify every objection, question, policy challenge, friction point, or specific office situation raised by the patient.

2. SOP TRIGGER IDENTIFICATION & DYNAMIC AUDIT TABLE:
   Cross-reference all detected objections against the 41 rules in the SOP Playbook above.
   For EVERY triggered situation, add an entry to 'sop_audit_table':
   - 'sop_id': Exact rule identifier (e.g. 'sop_external_xrays', 'sop_prepayment_rebuttal', 'sop_cost_root_canal', 'sop_balance_due').
   - 'sop_title': Clean human-readable title.
   - 'section': Playbook section.
   - 'patient_trigger_quote': Verbatim quote of what the caller said.
   - 'trainee_actual_quote': Verbatim quote of the trainee's actual response.
   - 'verdict': One of 'Adhered', 'Partially Adhered', 'Violated', or 'Missed Opportunity'.
   - 'violation_details': Explain specifically what was missing, breached, or done well according to the playbook.
   - 'approved_sop_verbiage': The official playbook verbiage and directives.
   If NO specific objections were triggered on the call, 'sop_audit_table' MUST be an empty array [].

3. STRICT INTERNAL CONSISTENCY RECONCILIATION:
   You MUST reconcile your scores so there are NO contradictory evaluations in the report card:
   - If any rule in 'sop_audit_table' has a verdict of 'Violated' or 'Missed Opportunity':
     * 'sop_adherence.score' CANNOT exceed 6/10 for 1 violation, and cannot exceed 4/10 for 2+ violations.
     * 'objection_handling.score' MUST be penalized proportionally (cannot be rated 9 or 10 if an objection was violated).
     * 'sop_adherence_summary.overall_sop_verdict' MUST be 'Partially Compliant' or 'Non-Compliant'.
     * The violation MUST be listed in 'improvement_areas' or 'missed_opportunities'.
   - If all detected triggers are 'Adhered':
     * 'sop_adherence.score' should be 8-10.
     * 'overall_sop_verdict' is 'Fully Compliant'.
   - If no objections occurred (clean standard inquiry):
     * 'sop_adherence.score' is based on standard greeting, note pauses, and general practice protocols (typically 8-10).
     * 'overall_sop_verdict' is 'Fully Compliant'.
   - Overall Score (1 to 100) must reflect the weighted composite:
     Rapport 10%, Discovery 15%, SOP Adherence 25%, Communication 10%, Objection Handling 20%, Recommendation Quality 10%, Compliance 10%.
"""


SCENARIO_PROMPTS = {
    "sbi": SYSTEM_PROMPT_SBI,
    "wtw": SYSTEM_PROMPT_WTW,
    "live call": SYSTEM_PROMPT_LIVE_CALL,
    "live-call": SYSTEM_PROMPT_LIVE_CALL,
    "health-insurance-live-call": SYSTEM_PROMPT_LIVE_CALL,
    "two-brothers-live-call": SYSTEM_PROMPT_TWO_BROTHERS,
    "two-brothers": SYSTEM_PROMPT_TWO_BROTHERS,
    "two_brothers": SYSTEM_PROMPT_TWO_BROTHERS,
    "two-brothers-organic-farms": SYSTEM_PROMPT_TWO_BROTHERS,
    "tbof": SYSTEM_PROMPT_TWO_BROTHERS,
    "motor-claim": SYSTEM_PROMPT_MOTOR_CLAIM,
    "motor_claim": SYSTEM_PROMPT_MOTOR_CLAIM,
    "motor-claim-copilot": SYSTEM_PROMPT_MOTOR_CLAIM,
    "motor-claim-agent": SYSTEM_PROMPT_MOTOR_CLAIM,
    "zurich-kotak-motor-claim": SYSTEM_PROMPT_MOTOR_CLAIM,
    "shield-claim": SYSTEM_PROMPT_MOTOR_CLAIM,
    "dental_scheduling": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-scheduling": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_emergency": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-emergency": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_emergency_triage": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-emergency-triage": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_price_shopper": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-price-shopper": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_frontdesk_compliance": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-frontdesk-compliance": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_clinical_objections": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-clinical-objections": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_insurance_copay": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-insurance-copay": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_insurance_verification": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-insurance-verification": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_implant_consult": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-implant-consult": SYSTEM_PROMPT_DENTAL_COACH,
    "dental_records_transfer": SYSTEM_PROMPT_DENTAL_COACH,
    "dental-records-transfer": SYSTEM_PROMPT_DENTAL_COACH,
    "custom_scenario": SYSTEM_PROMPT_DENTAL_COACH,
    "autocoach_dental": SYSTEM_PROMPT_DENTAL_COACH,
    "autocoach": SYSTEM_PROMPT_DENTAL_COACH,
}

CAREER_EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "student_name": {
            "type": "STRING",
            "description": "Name of the student/caller. If not mentioned or unknown, use 'Student' or 'Unknown'."
        },
        "current_status": {
            "type": "STRING",
            "description": "What the student is studying or doing currently (e.g. B.Sc, working, finished high school)."
        },
        "next_study_program": {
            "type": "STRING",
            "description": "What course or graduation program they are looking to pursue next (e.g. Master in CS, MBA)."
        },
        "plans_foreign_institutes": {
            "type": "STRING",
            "description": "Details about their plans to join foreign universities/institutes (e.g. Target countries, specific universities, or if they are undecided)."
        },
        "active_search_status": {
            "type": "STRING",
            "description": "Whether they are actively looking for opportunities/admissions right now (e.g. 'Actively searching', 'Just exploring', 'Not interested')."
        },
        "conviction_tier": {
            "type": "STRING",
            "description": "Assign one of the following priority tiers:\n"
                           "- 'Tier A' (High Potential): Highly active search, plans to study abroad within 1 year, clear graduation goals, responsive and interested in admissions/consultancy. Needs immediate follow-up.\n"
                           "- 'Tier B' (Medium Potential): Interested in studying abroad but timeline is longer (e.g. 2+ years) or budget/target is undecided. Needs nurturing.\n"
                           "- 'Tier C' (Low Potential): Unclear future plans, not planning/interested in joining foreign institutes, or unresponsive/uninterested. Low priority.\n"
                           "- 'Tier D' (Not Interested / Bad Fit): Explicitly stated they have no plans or interest in foreign education, or requested not to be contacted. Do not follow up."
        },
        "conviction_rationale": {
            "type": "STRING",
            "description": "A clear, concise explanation justifying the assigned conviction tier based on their answers."
        }
    },
    "required": [
        "student_name",
        "current_status",
        "next_study_program",
        "plans_foreign_institutes",
        "active_search_status",
        "conviction_tier",
        "conviction_rationale"
    ]
}

CAREER_EXTRACTION_SYSTEM_PROMPT = """You are an expert career intake analyst.
Your task is to analyze the conversation transcript between a Career Support Representative and a student.
Extract the student's current status, future study plans, plans for foreign education, and their readiness level.

CRITICAL INSTRUCTIONS FOR MULTILINGUAL TRANSCRIPTS:
- The conversation might be in English, a regional Indian language (e.g. Hindi, Malayalam, Tamil, Telugu, etc.), or a mix of languages (e.g. Hinglish).
- You MUST analyze and understand the conversation regardless of the language used.
- All extracted details (student_name, current_status, next_study_program, plans_foreign_institutes, active_search_status, conviction_rationale) MUST be written in English. Translate any non-English replies or details from the transcript to clear English for the database.

Assess how promising the student is as a lead/customer for a study-abroad consultancy, and assign them a conviction tier (Tier A, Tier B, Tier C, or Tier D) with a clear, professional rationale."""


# ──────────────────────────────────────────────────────────────
#  Evaluation Service Interface and Implementation
# ──────────────────────────────────────────────────────────────

class IEvaluationService(ABC):
    """
    Interface for chat transcript evaluation (Interface Segregation).
    """
    @abstractmethod
    async def evaluate_chat_history(
        self, chat_history_str: Optional[str], scenario: Optional[str] = "sbi"
    ) -> Tuple[Optional[dict], int]:
        """
        Evaluates a chat transcript and returns (report_card_dict, overall_score).
        Returns (None, 0) on failure.
        """
        pass

    @abstractmethod
    async def extract_career_details(
        self, chat_history_str: Optional[str]
    ) -> Optional[dict]:
        """
        Extracts structured student/career details and assigns conviction tier.
        Returns None on failure.
        """
        pass


class GeminiEvaluationService(IEvaluationService):
    """
    Gemini-backed evaluation service (migrated from report-server/services/gemini.py).
    Calls the Gemini API with structured JSON output to generate a QA report card.
    """

    async def evaluate_chat_history(
        self, chat_history_str: Optional[str], scenario: Optional[str] = "sbi"
    ) -> Tuple[Optional[dict], int]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.error("Gemini API key not configured.")
            return None, 0

        is_dental = bool(scenario and (scenario.startswith("dental") or "autocoach" in scenario.lower() or scenario == "custom_scenario"))
        transcript = self._format_transcript(chat_history_str, is_dental=is_dental)

        if is_dental:
            model_name = settings.GEMINI_EVALUATION_MODEL
            system_prompt = SCENARIO_PROMPTS.get(scenario, SYSTEM_PROMPT_DENTAL_COACH)
            response_schema = GEMINI_DENTAL_QA_REPORT_SCHEMA
            generation_config: dict[str, Any] = {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
                "thinkingConfig": {
                    "thinkingLevel": "high"
                }
            }
        else:
            model_name = "gemini-2.5-flash"
            system_prompt = SCENARIO_PROMPTS.get(scenario or "sbi", SYSTEM_PROMPT_SBI)
            response_schema = GEMINI_QA_REPORT_SCHEMA
            generation_config = {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            }

        prompt = f"{system_prompt}\n\nHere is the conversation transcript:\n{transcript}"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": generation_config
        }

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        response_json = response.json()
                        candidates = response_json.get("candidates", [])
                        if not candidates:
                            logger.error(f"No candidates returned from Gemini: {response_json}")
                            return None, 0

                        content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if not content_text:
                            logger.error("Empty text in Gemini response candidate.")
                            return None, 0

                        report_card = json.loads(content_text.strip())
                        overall_score = report_card.get("overall_score", 0)
                        return report_card, overall_score
                    
                    if response.status_code in [429, 500, 502, 503, 504]:
                        logger.warning(
                            f"Gemini API returned status {response.status_code}. "
                            f"Attempt {attempt + 1} of {max_retries}. Retrying..."
                        )
                    else:
                        logger.error(f"Gemini API returned unrecoverable status {response.status_code}: {response.text}")
                        return None, 0
                        
            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.warning(f"Error during Gemini call attempt {attempt + 1}: {e}")
                
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                await asyncio.sleep(sleep_time)
                
        logger.error("Gemini API call failed after max retries.")
        return None, 0

    async def extract_career_details(
        self, chat_history_str: Optional[str]
    ) -> Optional[dict]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.error("Gemini API key not configured for career data extraction.")
            return None

        transcript = self._format_transcript_career(chat_history_str)
        prompt = f"{CAREER_EXTRACTION_SYSTEM_PROMPT}\n\nHere is the conversation transcript:\n{transcript}"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": CAREER_EXTRACTION_SCHEMA
            }
        }

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        response_json = response.json()
                        candidates = response_json.get("candidates", [])
                        if not candidates:
                            logger.error(f"No candidates returned from Gemini during career extraction: {response_json}")
                            return None

                        content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if not content_text:
                            logger.error("Empty text in Gemini response candidate during career extraction.")
                            return None

                        extracted_data = json.loads(content_text.strip())
                        return extracted_data
                    
                    if response.status_code in [429, 500, 502, 503, 504]:
                        logger.warning(
                            f"Gemini API returned status {response.status_code} during career extraction. "
                            f"Attempt {attempt + 1} of {max_retries}. Retrying..."
                        )
                    else:
                        logger.error(f"Gemini API returned unrecoverable status {response.status_code} during career extraction: {response.text}")
                        return None
                        
            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.warning(f"Error during Gemini career extraction call attempt {attempt + 1}: {e}")
                
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                await asyncio.sleep(sleep_time)
                
        logger.error("Gemini API call for career extraction failed after max retries.")
        return None

    @staticmethod
    def _format_transcript(chat_history_str: Optional[str], is_dental: bool = False) -> str:
        """Parses LiveKit chat history JSON into a readable transcript, including telemetry if available."""
        if not chat_history_str:
            return "No transcript available."
        try:
            data = json.loads(chat_history_str)
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            lines = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "type" in item and item.get("type") != "message":
                    continue
                role = item.get("role")
                if role == "system":
                    continue

                content_list = item.get("content", [])
                text = ""
                if isinstance(content_list, list):
                    text = " ".join([str(c) for c in content_list if isinstance(c, str)])
                elif isinstance(content_list, str):
                    text = content_list
                elif isinstance(item.get("text"), str):
                    text = item.get("text", "")

                if not text.strip():
                    continue

                if is_dental:
                    speaker = "Front Desk Trainee" if role in ["user", "trainee", "human"] else "Patient"
                else:
                    speaker = "Ira Representative" if role == "user" else "AI Customer"
                lines.append(f"{speaker}: {text.strip()}")

            transcript_text = "\n".join(lines)

            # Extract runtime telemetry & copilot state if provided
            if isinstance(data, dict) and data.get("claim_context"):
                ctx = data.get("claim_context")
                if isinstance(ctx, dict):
                    telemetry_parts = ["\n[RUNTIME TELEMETRY & COPILOT STATE]"]
                    if ctx.get("claim_number"):
                        telemetry_parts.append(f"• Claim Number: {ctx.get('claim_number')}")
                    if ctx.get("policy_number"):
                        telemetry_parts.append(f"• Policy Number: {ctx.get('policy_number')} (Identity Verified)")
                    if ctx.get("customer_name"):
                        telemetry_parts.append(f"• Insured Customer Name: {ctx.get('customer_name')}")
                    if ctx.get("vehicle"):
                        telemetry_parts.append(f"• Vehicle Registration / Model: {ctx.get('vehicle')}")

                    # Disclaimers
                    disclaimers = ctx.get("disclaimers_checked")
                    if isinstance(disclaimers, list) and any(disclaimers):
                        telemetry_parts.append("• Recording Disclosure Spoken: Yes (verified by copilot)")
                    elif disclaimers is not None:
                        telemetry_parts.append("• Recording Disclosure Spoken: Not verified on interface")

                    # Compliance Log
                    comp_log = ctx.get("compliance_log")
                    if isinstance(comp_log, list) and len(comp_log) > 0:
                        total_alerts = len(comp_log)
                        cleared_count = sum(1 for c in comp_log if isinstance(c, dict) and c.get("isClear"))
                        uncorrected_count = total_alerts - cleared_count
                        log_summaries = []
                        for c in comp_log[:5]:
                            if isinstance(c, dict):
                                flag_name = c.get("ruleCode") or c.get("flag") or "Alert"
                                is_clr = "Corrected on call" if c.get("isClear") else "Uncorrected"
                                log_summaries.append(f"{flag_name} ({is_clr})")
                        comp_desc = f"{total_alerts} alert(s) raised, {cleared_count} corrected on call"
                        if uncorrected_count > 0:
                            comp_desc += f", {uncorrected_count} active/uncorrected"
                        if log_summaries:
                            comp_desc += f" -> [{', '.join(log_summaries)}]"
                        telemetry_parts.append(f"• Compliance Alerts Log: {comp_desc}")

                    # Mood History
                    mood_history = ctx.get("mood_history")
                    if isinstance(mood_history, list) and len(mood_history) > 0:
                        mood_steps = []
                        for m in reversed(mood_history):
                            if isinstance(m, dict) and m.get("mood"):
                                mood_steps.append(m.get("mood"))
                            elif isinstance(m, str):
                                mood_steps.append(m)
                        if mood_steps:
                            telemetry_parts.append(f"• Customer Mood Progression: {' -> '.join(mood_steps)}")

                    telemetry_parts.append("[END OF RUNTIME TELEMETRY]\n")
                    return "\n".join(telemetry_parts) + "\n" + transcript_text

            return transcript_text
        except Exception as e:
            return f"Error parsing transcript: {e}"

    @staticmethod
    def _format_transcript_career(chat_history_str: Optional[str]) -> str:
        """Parses LiveKit chat history JSON into a readable transcript for career agent."""
        if not chat_history_str:
            return "No transcript available."
        try:
            data = json.loads(chat_history_str)
            items = data.get("items", [])
            lines = []
            for item in items:
                if item.get("type") != "message":
                    continue
                role = item.get("role")
                if role == "system":
                    continue

                content_list = item.get("content", [])
                text = ""
                if isinstance(content_list, list):
                    text = " ".join([str(c) for c in content_list if isinstance(c, str)])
                elif isinstance(content_list, str):
                    text = content_list

                if not text.strip():
                    continue

                speaker = "Student" if role == "user" else "Career Representative"
                lines.append(f"{speaker}: {text.strip()}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error parsing transcript: {e}"
