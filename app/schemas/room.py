from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class RoomCreate(BaseModel):
    """
    Schema for creating a new LiveKit room.
    """
    name: str = Field(..., description="Unique name for the room")
    empty_timeout: int = Field(300, description="Time in seconds to wait before closing an empty room")
    max_participants: int = Field(20, description="Maximum number of participants allowed in the room")
    metadata: Optional[str] = Field(None, description="Optional metadata string for the room")

class ParticipantInfo(BaseModel):
    """
    Schema representing a participant in the room.
    """
    identity: str
    name: Optional[str] = None
    state: str
    joined_at: int
    metadata: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)

class RoomResponse(BaseModel):
    """
    Schema for room information returned to clients.
    """
    name: str
    sid: str
    empty_timeout: int
    max_participants: int
    num_participants: int
    metadata: Optional[str] = None
    active_participants: List[ParticipantInfo] = Field(default_factory=list)
