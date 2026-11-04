"""
Protocol Loader Utility for Dental QA Engine
Loads general 41-rule dental SOPs and clinic-specific protocols into memory.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

PROTOCOLS_DIR = Path(__file__).resolve().parent

def load_sop_rules() -> List[Dict[str, Any]]:
    """Loads all 41 standard dental SOP rules from sop_rules.json."""
    sop_path = PROTOCOLS_DIR / "sop_rules.json"
    if not sop_path.exists():
        raise FileNotFoundError(f"SOP rules file not found at: {sop_path}")
    with open(sop_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_citrus_smiles_protocol() -> Dict[str, Any]:
    """Loads Citrus Smiles Dental clinic protocol (Tier 1 & Tier 2)."""
    citrus_path = PROTOCOLS_DIR / "citrus_smiles_protocol.json"
    if not citrus_path.exists():
        raise FileNotFoundError(f"Citrus Smiles protocol file not found at: {citrus_path}")
    with open(citrus_path, "r", encoding="utf-8") as f:
        return json.load(f)

def format_sop_rules_for_prompt() -> str:
    """Formats SOP rules into a clean markdown prompt reference."""
    rules = load_sop_rules()
    lines = ["# DENTAL FRONT DESK STANDARD OPERATING PROCEDURES (41 RULES)"]
    for r in rules:
        lines.append(f"\n### [{r.get('id')}] {r.get('title')}")
        lines.append(f"- **Section:** {r.get('section')}")
        lines.append(f"- **Trigger Condition:** {r.get('trigger_condition')}")
        lines.append(f"- **Approved Verbiage / Directives:**\n{r.get('approved_verbiage')}")
        lines.append(f"- **Core Rule:** {r.get('key_rule')}")
    return "\n".join(lines)

def format_citrus_protocol_for_prompt() -> str:
    """Formats Citrus Smiles protocol into structured prompt reference."""
    data = load_citrus_smiles_protocol()
    lines = [
        f"# CLINIC SPECIFIC PROTOCOL: {data.get('clinic_name')} ({data.get('location')})",
        f"- **Lead Provider:** {data.get('lead_provider')}",
        f"- **Office Manager:** {data.get('office_manager')}",
        "\n## TIER 1: NON-NEGOTIABLE HARD RULES (ALWAYS ACTIVE - CRITICAL FAIL IF VIOLATED)"
    ]
    for r in data.get("tier_1_hard_rules", []):
        lines.append(f"\n### [{r.get('rule_id')}] {r.get('title')}")
        lines.append(f"- **Rule:** {r.get('rule_specification')}")
        lines.append(f"- **Audit Guidance:** {r.get('audit_guidance')}")

    lines.append("\n## TIER 2: TRIGGER-BASED RULES (EVALUATED ONLY IF TOPIC OCCURS IN CALL)")
    for r in data.get("tier_2_trigger_rules", []):
        lines.append(f"\n### [{r.get('rule_id')}] {r.get('title')}")
        lines.append(f"- **Trigger:** {r.get('trigger_condition')}")
        lines.append(f"- **Rule:** {r.get('rule_specification')}")
        lines.append(f"- **Audit Guidance:** {r.get('audit_guidance')}")

    return "\n".join(lines)

