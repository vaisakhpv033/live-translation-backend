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

    # LiveKit credentials
    LIVEKIT_URL: str = Field(description="The WebSocket/HTTP URL for LiveKit server")
    LIVEKIT_API_KEY: str = Field(description="LiveKit API Key")
    LIVEKIT_API_SECRET: str = Field(description="LiveKit API Secret")

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
