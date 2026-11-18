"""
Unified, Rate-Limit Resilient Gemini API Caller for Dental QA Engine.
Features:
- Global concurrency throttling (asyncio.Semaphore) to prevent 429 burst overruns.
- Dynamic Retry-After header parsing for Google Gemini rate limits (HTTP 429).
- Exponential backoff with random jitter to prevent thundering herd retries.
- Safe extraction of non-thought candidate text.
- Standardized token usage accounting.
"""

import asyncio
import json
import logging
import random
from typing import Any, Dict, Optional, Tuple, Type, Union
import httpx
from pydantic import BaseModel, ValidationError

from app.modules.dental_qa.config import settings
from app.modules.dental_qa.schemas.gemini_schema import to_gemini_schema

logger = logging.getLogger("dental_qa_engine.gemini_caller")

_gemini_semaphore: Optional[asyncio.Semaphore] = None


def get_gemini_semaphore() -> asyncio.Semaphore:
    """Returns the singleton concurrency semaphore for Gemini calls."""
    global _gemini_semaphore
    if _gemini_semaphore is None:
        concurrency = getattr(settings, "MAX_CONCURRENT_GEMINI_CALLS", 2)
        _gemini_semaphore = asyncio.Semaphore(concurrency)
    return _gemini_semaphore


async def execute_gemini_structured_call(
    prompt: str,
    schema: Union[Type[BaseModel], dict],
    stage_name: str = "Dental QA",
    thinking_level: Optional[str] = None,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Tuple[Any, dict]:
    """
    Executes a structured JSON generation call to Google Gemini with:
    1. Concurrency throttling (semaphore).
    2. Retry-After header awareness and exponential backoff with jitter on 429 / 5xx.
    3. Proper socket timeout configuration.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    model = model_name or settings.GEMINI_MODEL
    effective_thinking = thinking_level or settings.GEMINI_THINKING_LEVEL

    # Resolve schema dict and validator
    if isinstance(schema, dict):
        response_schema = schema
        validator = None
    else:
        response_schema = to_gemini_schema(schema)
        validator = schema

    url = f"{settings.GEMINI_API_BASE_URL}/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
            "thinkingConfig": {
                "thinkingLevel": effective_thinking,
            },
        },
    }

    read_timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
    timeout_config = httpx.Timeout(
        timeout=read_timeout,
        connect=20.0,
        read=read_timeout,
        write=30.0,
        pool=30.0,
    )

    retries = max_retries or getattr(settings, "MAX_RETRIES", 5)
    semaphore = get_gemini_semaphore()

    for attempt in range(retries):
        async with semaphore:
            try:
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    res = await client.post(url, headers=headers, json=payload)

                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            raise ValueError(f"No candidates returned in Gemini response: {data}")

                        parts = candidates[0].get("content", {}).get("parts", [])
                        raw_text = "".join(p.get("text", "") for p in parts if not p.get("thought", False))
                        if not raw_text.strip():
                            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
                            raise ValueError(f"Empty text in Gemini response candidate (finishReason: {finish_reason})")

                        parsed_dict = json.loads(raw_text.strip())
                        usage = data.get("usageMetadata", {})

                        if validator:
                            return validator.model_validate(parsed_dict), usage
                        return parsed_dict, usage

                    # Handle Rate Limits (429) & Server Errors (5xx)
                    if res.status_code in [429, 500, 502, 503, 504]:
                        error_detail = ""
                        try:
                            err_json = res.json()
                            error_detail = err_json.get("error", {}).get("message", res.text[:200])
                        except Exception:
                            error_detail = res.text[:200]

                        retry_after_hdr = res.headers.get("retry-after")
                        if retry_after_hdr:
                            try:
                                sleep_sec = float(retry_after_hdr) + random.uniform(0.5, 2.0)
                            except ValueError:
                                sleep_sec = (3.0 * (2.0 ** attempt)) + random.uniform(0.5, 2.0)
                        else:
                            # 429 requires a longer pause than generic errors to clear quota window
                            base = 4.0 if res.status_code == 429 else 2.0
                            sleep_sec = (base * (2.0 ** attempt)) + random.uniform(0.5, 2.0)

                        logger.warning(
                            f"Gemini {stage_name} returned status {res.status_code} ({error_detail}) on attempt {attempt + 1}/{retries}. "
                            f"Backing off for {sleep_sec:.1f}s before retry..."
                        )
                        await asyncio.sleep(sleep_sec)
                        continue
                    else:
                        raise RuntimeError(f"Unrecoverable error in {stage_name} (status {res.status_code}): {res.text}")

            except (httpx.RequestError, json.JSONDecodeError, ValueError, ValidationError) as e:
                err_msg = str(e) or "Socket/Read Timeout"
                logger.warning(f"{stage_name} attempt {attempt + 1} failed: {type(e).__name__}: {err_msg}")
                if attempt < retries - 1:
                    sleep_sec = (2.0 * (2.0 ** attempt)) + random.uniform(0.5, 1.5)
                    await asyncio.sleep(sleep_sec)

    raise TimeoutError(f"{stage_name} failed after {retries} retries.")
