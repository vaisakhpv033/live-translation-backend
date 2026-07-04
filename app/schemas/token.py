from pydantic import BaseModel, Field
from typing import Optional

class TokenRequest(BaseModel):
    """
    Schema for request to generate a LiveKit join token.
    """
    identity: str = Field(..., description="Unique participant identity (e.g. email, user ID)")
    username: Optional[str] = Field(None, description="Optional friendly display name")
    speaking_language: str = Field("en", description="BCP-47 code of the language spoken by the user (e.g., 'en', 'ml')")
    target_language: Optional[str] = Field(None, description="Optional BCP-47 code of the target translation language (e.g., 'ml', 'en')")

class TokenResponse(BaseModel):
    """
    Schema for generated join token response.
    """
    token: str = Field(..., description="Signed JWT Access Token for LiveKit connection")
    room_name: str = Field(..., description="Name of the room the token is for")
    identity: str = Field(..., description="Participant identity token was generated for")
