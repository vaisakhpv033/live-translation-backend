# SPDX-License-Identifier: MIT
"""Pronunciation Assessment Module for FastAPI Backends."""

from .router import router
from .service import BasePronunciationService, get_pronunciation_service

__all__ = ["router", "BasePronunciationService", "get_pronunciation_service"]
