from typing import List, Tuple, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class ChatMessageInput(BaseModel):
    user_query: str = Field(..., description="The user's query or message.")
    report_id: str = Field(..., description="The ID of the report being discussed.")
    username: str = Field(..., description="The username of the user making the request.")
    session_id: Optional[str] = Field(None, description="The ID of the current chat session. If None, a new session might be initiated.")

class ChatMessageOutput(BaseModel):
    ai_response: str = Field(..., description="The AI agent's response.")
    session_id: str = Field(..., description="The ID of the chat session.")
    original_query: str = Field(..., description="The original user query this response addresses.")

class ChatHistoryItem(BaseModel):
    role: str # "user" or "ai"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When this message was created.")

class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for the chat session.")
    report_id: str = Field(..., description="The ID of the report this session pertains to.")
    username: str = Field(..., description="The username of the user who owns this session.")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When this session was created.")
    history: List[ChatHistoryItem] = Field(default_factory=list, description="A list of chat messages, Tuples of (role, content).")
    # report_content: Optional[str] = Field(None, description="The actual content of the report, loaded on demand.") # Consider if this should be here or managed separately

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "report_id": "report_final_001",
                "username": "john_doe",
                "created_at": "2024-01-15T10:30:00Z",
                "history": [
                    {"role": "user", "content": "What is the main conclusion of this report?", "timestamp": "2024-01-15T10:30:00Z"},
                    {"role": "ai", "content": "The main conclusion is X, based on Y and Z.", "timestamp": "2024-01-15T10:30:15Z"}
                ]
            }
        }

class UserHistoryEntry(BaseModel):
    username: str = Field(..., description="The username of the user.")
    activity_type: str = Field(..., description="Type of activity (e.g., 'chat_message', 'session_created').")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When this activity occurred.")
    session_id: Optional[str] = Field(None, description="Associated session ID if applicable.")
    report_id: Optional[str] = Field(None, description="Associated report ID if applicable.")
    details: dict = Field(default_factory=dict, description="Additional details about the activity.")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "activity_type": "chat_message",
                "timestamp": "2024-01-15T10:30:00Z",
                "session_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "report_id": "report_final_001",
                "details": {"query": "What is the main conclusion?", "response_length": 150}
            }
        } 