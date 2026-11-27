"""Model-aware token cost calculation for LiveKit STS voice agents and Gemini QA evaluators."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Official Gemini Developer API Paid Tier rates (USD per 1,000,000 tokens)
LIVE_MODEL_RATES: Dict[str, Dict[str, float]] = {
    "gemini-3.8-live": {
        "text_input": 0.75,
        "cached_text_input": 0.75,
        "audio_input": 3.00,
        "cached_audio_input": 3.00,
        "audio_output": 12.00,
        "text_output": 4.50,
    },
    "gemini-3.8-live-extended-thinking": {
        "text_input": 0.75,
        "cached_text_input": 0.75,
        "audio_input": 3.00,
        "cached_audio_input": 3.00,
        "audio_output": 12.00,
        "text_output": 4.50,
    },
    "gemini-3.1-flash-live-preview": {
        "text_input": 0.75,
        "cached_text_input": 0.75,
        "audio_input": 3.00,
        "cached_audio_input": 3.00,
        "audio_output": 12.00,
        "text_output": 4.50,
    },
}

QA_MODEL_RATES: Dict[str, Dict[str, float]] = {
    "gemini-4-hydrogen": {
        "input": 1.50,
        "cached_input": 0.075,
        "output": 7.50,
    },
    "gemini-3.8-flash": {
        "input": 0.75,
        "cached_input": 0.075,
        "output": 3.75,
    },
}


def _safe_int(val: Any) -> int:
    try:
        return max(0, int(val or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_model_id(model_name: Optional[str], default: str) -> str:
    clean = (model_name or "").strip().lower()
    if clean.startswith("models/"):
        clean = clean[len("models/") :]
    if clean.startswith("google/"):
        clean = clean[len("google/") :]
    return clean or default


def _resolve_live_rates(model_name: Optional[str]) -> Dict[str, float]:
    norm = _normalize_model_id(model_name, "gemini-3.8-live")
    if norm in LIVE_MODEL_RATES:
        return LIVE_MODEL_RATES[norm]
    for key, rates in LIVE_MODEL_RATES.items():
        if key in norm or norm in key:
            return rates
    return LIVE_MODEL_RATES["gemini-3.8-live"]


def _resolve_qa_rates(model_name: Optional[str]) -> Dict[str, float]:
    norm = _normalize_model_id(model_name, "gemini-4-hydrogen")
    if norm in QA_MODEL_RATES:
        return QA_MODEL_RATES[norm]
    for key, rates in QA_MODEL_RATES.items():
        if key in norm or norm in key:
            return rates
    return QA_MODEL_RATES["gemini-4-hydrogen"]


def compute_agent_usage_cost_usd(
    model_usage_items: Optional[List[Dict[str, Any]]],
    fallback_model: Optional[str] = "gemini-3.8-live",
) -> float:
    """Computes total LiveKit/Gemini Live voice call USD cost without double-counting modalities."""
    if not isinstance(model_usage_items, list) or not model_usage_items:
        return 0.0

    total_cost = 0.0
    for item in model_usage_items:
        if not isinstance(item, dict):
            continue

        rates = _resolve_live_rates(item.get("model") or fallback_model)

        inp_total = _safe_int(
            item.get("input_tokens")
            or item.get("prompt_tokens")
            or item.get("llm_input_tokens")
        )
        inp_audio = _safe_int(
            item.get("input_audio_tokens") or item.get("llm_input_audio_tokens")
        )
        inp_text = _safe_int(item.get("input_text_tokens"))
        if inp_text == 0 and inp_total > inp_audio:
            inp_text = max(0, inp_total - inp_audio)

        inp_cached_audio = _safe_int(item.get("input_cached_audio_tokens"))
        inp_cached_text = _safe_int(item.get("input_cached_text_tokens"))
        inp_cached_total = _safe_int(item.get("input_cached_tokens"))
        if inp_cached_total > 0 and inp_cached_audio == 0 and inp_cached_text == 0:
            inp_cached_text = min(inp_cached_total, inp_text)
            remaining_cached = max(0, inp_cached_total - inp_cached_text)
            inp_cached_audio = min(remaining_cached, inp_audio)

        uncached_audio_in = max(0, inp_audio - inp_cached_audio)
        uncached_text_in = max(0, inp_text - inp_cached_text)

        out_total = _safe_int(
            item.get("output_tokens")
            or item.get("completion_tokens")
            or item.get("llm_output_tokens")
        )
        out_audio = _safe_int(
            item.get("output_audio_tokens") or item.get("llm_output_audio_tokens")
        )
        out_text = _safe_int(item.get("output_text_tokens"))
        out_reasoning = _safe_int(
            item.get("output_reasoning_tokens") or item.get("reasoning_tokens")
        )
        # output_tokens already includes output_audio_tokens + output_text_tokens + output_reasoning_tokens
        if out_text == 0 and out_reasoning == 0:
            effective_text_out = max(0, out_total - out_audio)
        else:
            effective_text_out = max(out_text + out_reasoning, max(0, out_total - out_audio))

        entry_cost = (
            (uncached_text_in / 1_000_000.0) * rates["text_input"]
            + (inp_cached_text / 1_000_000.0) * rates["cached_text_input"]
            + (uncached_audio_in / 1_000_000.0) * rates["audio_input"]
            + (inp_cached_audio / 1_000_000.0) * rates["cached_audio_input"]
            + (out_audio / 1_000_000.0) * rates["audio_output"]
            + (effective_text_out / 1_000_000.0) * rates["text_output"]
        )
        total_cost += entry_cost

    return round(total_cost, 6)


def compute_qa_cost_usd(
    model_name: Optional[str],
    prompt_tokens: int,
    cached_tokens: int,
    candidates_tokens: int,
    thoughts_tokens: int,
) -> float:
    """Computes Gemini QA evaluation USD cost with implicit cache pricing and zero double-counting."""
    rates = _resolve_qa_rates(model_name)
    safe_prompt = max(0, int(prompt_tokens or 0))
    safe_cached = min(safe_prompt, max(0, int(cached_tokens or 0)))
    uncached_prompt = max(0, safe_prompt - safe_cached)
    total_output = max(0, int(candidates_tokens or 0)) + max(0, int(thoughts_tokens or 0))

    cost = (
        (uncached_prompt / 1_000_000.0) * rates["input"]
        + (safe_cached / 1_000_000.0) * rates["cached_input"]
        + (total_output / 1_000_000.0) * rates["output"]
    )
    return round(cost, 6)
