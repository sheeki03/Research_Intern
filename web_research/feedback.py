from typing import List, Dict, Any
import openai
import json
from src.config import SYSTEM_PROMPT
from src.openrouter import OpenRouterClient
from .ai.providers import get_client_response


async def generate_feedback(report: str, client: OpenRouterClient) -> Dict[str, Any]:
    """Generate feedback on a research report."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Please provide feedback on this research report:\n\n{report}"}
    ]
    
    # Run OpenAI call in thread pool since it's synchronous

    response = await get_client_response(
        client=client,
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
    )

    # Parse the JSON response
    try:
        return response.get("questions", [])
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response}")
        return []
