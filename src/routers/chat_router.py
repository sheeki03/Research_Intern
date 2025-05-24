from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Optional

from src.models.chat_models import ChatMessageInput, ChatMessageOutput, ChatSession, ChatHistoryItem

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

# In-memory store for chat sessions for now. 
# In a production scenario, this would be a database (e.g., Redis, PostgreSQL).
chat_sessions: Dict[str, ChatSession] = {}

def get_or_create_session(report_id: str, session_id: Optional[str] = None) -> ChatSession:
    """Retrieves an existing chat session or creates a new one."""
    if session_id and session_id in chat_sessions:
        if chat_sessions[session_id].report_id == report_id:
            return chat_sessions[session_id]
        else:
            # This case should ideally not happen if session_id is correctly managed client-side per report
            raise HTTPException(status_code=400, detail=f"Session ID {session_id} exists but for a different report.")
    
    # Create a new session if no valid session_id is provided or found
    new_session = ChatSession(report_id=report_id)
    chat_sessions[new_session.session_id] = new_session
    return new_session

@router.post("/ask", response_model=ChatMessageOutput)
async def ask_question(
    payload: ChatMessageInput = Body(...)
):
    """
    Receives a user's question about a report, interacts with an AI (currently echo), 
    and returns the AI's response.
    Manages chat session history.
    """
    session = get_or_create_session(report_id=payload.report_id, session_id=payload.session_id)

    # Add user message to history
    session.history.append(ChatHistoryItem(role="user", content=payload.user_query))

    # --- AI Logic Placeholder --- 
    # For Task 3 (Echo AI), this will be simple. For Task 6, this will involve LLM call.
    # For now, let's make it clear it's a placeholder for the echo functionality.
    ai_response_content = f"Echo: You asked about report '{payload.report_id}': '{payload.user_query}'"
    # --- End AI Logic Placeholder ---

    # Add AI response to history
    session.history.append(ChatHistoryItem(role="ai", content=ai_response_content))

    # Update the session in our in-memory store (important if ChatSession is mutable and copied by value)
    chat_sessions[session.session_id] = session

    return ChatMessageOutput(
        ai_response=ai_response_content,
        session_id=session.session_id,
        original_query=payload.user_query
    )

@router.get("/{session_id}/history", response_model=ChatSession)
async def get_chat_history(session_id: str):
    """Retrieves the chat history for a given session ID."""
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return chat_sessions[session_id]

# TODO:
# - Task 5: Integrate Report Context: 
#   - How to load report_content? (e.g., from file system, database based on report_id)
#   - Pass report_content to the AI logic.
# - Task 6: Integrate a Basic LLM for Q&A:
#   - Replace placeholder AI logic with actual LLM call.
#   - Manage LLM API keys and client setup.
# - Task 7: Implement Conversation History in Backend (LLM part):
#   - Ensure the LLM prompt includes relevant parts of session.history. 