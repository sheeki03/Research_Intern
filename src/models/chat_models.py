from typing import List, Tuple, Optional
from pydantic import BaseModel, Field
import uuid

class ChatMessageInput(BaseModel):
    user_query: str = Field(..., description="The user's query or message.")
    report_id: str = Field(..., description="The ID of the report being discussed.")
    session_id: Optional[str] = Field(None, description="The ID of the current chat session. If None, a new session might be initiated.")

class ChatMessageOutput(BaseModel):
    ai_response: str = Field(..., description="The AI agent's response.")
    session_id: str = Field(..., description="The ID of the chat session.")
    original_query: str = Field(..., description="The original user query this response addresses.")

class ChatHistoryItem(BaseModel):
    role: str # "user" or "ai"
    content: str

class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for the chat session.")
    report_id: str = Field(..., description="The ID of the report this session pertains to.")
    history: List[ChatHistoryItem] = Field(default_factory=list, description="A list of chat messages, Tuples of (role, content).")
    # report_content: Optional[str] = Field(None, description="The actual content of the report, loaded on demand.") # Consider if this should be here or managed separately

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "report_id": "report_final_001",
                "history": [
                    {"role": "user", "content": "What is the main conclusion of this report?"},
                    {"role": "ai", "content": "The main conclusion is X, based on Y and Z."}
                ]
            }
        } 