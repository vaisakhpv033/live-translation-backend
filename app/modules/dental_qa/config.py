"""
Configuration settings for the Dental QA Engine module.
Resilient loader: binds to app.core.config.get_settings(), with automatic
fallback to backend .env and os.environ.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root .env is loaded regardless of process working directory
BACKEND_DIR = Path(__file__).resolve().parents[3]
env_path = BACKEND_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


class DentalQAConfig:
    def __init__(self):
        self._app_settings = None

    def _get_app_settings(self):
        if self._app_settings is None:
            try:
                from app.core.config import get_settings
                self._app_settings = get_settings()
            except Exception:
                self._app_settings = None
        return self._app_settings

    @property
    def GEMINI_API_KEY(self) -> str:
        s = self._get_app_settings()
        if s and getattr(s, "GEMINI_API_KEY", None):
            return s.GEMINI_API_KEY
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def GEMINI_MODEL(self) -> str:
        s = self._get_app_settings()
        if s and getattr(s, "GEMINI_EVALUATION_MODEL", None):
            return s.GEMINI_EVALUATION_MODEL
        return os.getenv("GEMINI_EVALUATION_MODEL", "gemini-3.8-flash")

    GEMINI_THINKING_LEVEL: str = "high"
    HTTP_TIMEOUT_SECONDS: float = 120.0
    MAX_RETRIES: int = 3
    BACKOFF_FACTOR: float = 2.0
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"


settings = DentalQAConfig()
