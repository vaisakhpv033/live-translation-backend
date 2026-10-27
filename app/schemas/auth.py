from typing import Optional
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str = Field(..., description="Demo user username")
    password: str = Field(..., description="Demo user password")

class UserResponse(BaseModel):
    username: str = Field(..., description="Authenticated username")
    role: str = Field(default="admin", description="Assigned role")

class LoginResponse(BaseModel):
    token: str = Field(..., description="Signed JWT Bearer token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_at: int = Field(..., description="Unix timestamp (in seconds) when the token expires")
    user: UserResponse = Field(..., description="Authenticated user profile")

class VerifyTokenResponse(BaseModel):
    valid: bool
    user: Optional[UserResponse] = None
