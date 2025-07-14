from pydantic import BaseModel, Field
from typing import Optional

class VoiceClonerInput(BaseModel):
    """Input model for voice cloner functionality."""
    writing_example_1: str = Field(..., description="First writing example to analyze voice style")
    writing_example_2: str = Field(..., description="Second writing example to analyze voice style") 
    writing_example_3: str = Field(..., description="Third writing example to analyze voice style")
    new_piece_to_create: str = Field(..., description="Description of the new piece to create in the analyzed voice style")
    model: str = Field(..., description="AI model to use for voice cloning")
    username: str = Field(..., description="Username of the user making the request")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")

class VoiceClonerOutput(BaseModel):
    """Output model for voice cloner results."""
    final_piece: str = Field(..., description="The final voice-cloned piece")
    style_rules: str = Field(..., description="The extracted style rules used for voice cloning")
    confidence_score: int = Field(..., description="Confidence score (0-100) of how well the voice was cloned")
    iterations_completed: int = Field(..., description="Number of iterations completed during the refinement process")
    processing_time: float = Field(..., description="Time taken to process the request")