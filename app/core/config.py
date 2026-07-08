from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application configurations validated using Pydantic Settings.
    """
    PROJECT_NAME: str = "Translation Agent Backend"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8000

    # LiveKit credentials (Translation Agent)
    LIVEKIT_URL: str = Field(description="The WebSocket/HTTP URL for LiveKit server")
    LIVEKIT_API_KEY: str = Field(description="LiveKit API Key")
    LIVEKIT_API_SECRET: str = Field(description="LiveKit API Secret")

    # STS Agent LiveKit credentials (separate LiveKit project)
    STS_LIVEKIT_URL: str = Field(description="LiveKit URL for the STS agent project")
    STS_LIVEKIT_API_KEY: str = Field(description="LiveKit API Key for STS project")
    STS_LIVEKIT_API_SECRET: str = Field(description="LiveKit API Secret for STS project")

    # PostgreSQL Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://backend_user:backend_pass@localhost:5432/translation_backend",
        description="Async PostgreSQL connection string"
    )

    # Gemini API (for report evaluation)
    GEMINI_API_KEY: str = Field(description="Gemini API key for chat transcript evaluation")

    # CORS Settings
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins(self) -> list[str]:
        """
        Parses the comma-separated ALLOWED_ORIGINS string into a list of origins.
        """
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # Resolve schema-validated URL for LiveKit REST APIs
    @property
    def livekit_api_url(self) -> str:
        """
        Converts the WebSocket schema (wss:// or ws://) to HTTP/HTTPS as needed
        by the LiveKitAPI REST/Twirp client.
        """
        url = self.LIVEKIT_URL
        if url.startswith("wss://"):
            return url.replace("wss://", "https://")
        elif url.startswith("ws://"):
            return url.replace("ws://", "http://")
        return url

    @property
    def sts_livekit_api_url(self) -> str:
        """
        Converts the STS LiveKit WebSocket schema to HTTP/HTTPS for REST API usage.
        """
        url = self.STS_LIVEKIT_URL
        if url.startswith("wss://"):
            return url.replace("wss://", "https://")
        elif url.startswith("ws://"):
            return url.replace("ws://", "http://")
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached instance of the Settings object.
    """
    return Settings()
