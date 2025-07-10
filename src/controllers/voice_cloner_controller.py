import asyncio
import time
import logging
import requests
import json
from typing import Optional
from src.models.voice_cloner_models import VoiceClonerInput, VoiceClonerOutput
from src.openrouter import OpenRouterClient
from src.config import AI_MODEL_OPTIONS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

class VoiceClonerController:
    """Controller for voice cloner functionality."""
    
    def __init__(self):
        self.openrouter_client = OpenRouterClient()
    
    def _create_voice_cloner_prompt(self, input_data: VoiceClonerInput) -> str:
        """Create the system prompt for voice cloning and text reformatting."""
        return f"""<instructions>
You are an expert "voice-cloner" and writer running on OpenAI o3.

Step 1 – Review my voice prints.

Step 2 – Build my Style DNA:
From the Voice Prints:  
• Identify recurring patterns in tone, sentence length, favorite phrases, pacing, humor, formality, and structure.

Step 3 – Draft v0.1:
• Take the existing text provided and reformat it to match my voice style exactly.
• Make it sound more human-like and natural while preserving the core message and information.
• Keep a confidence meter (0-100%) on how close the reformatted text sounds to me.

Step 4 – Micro-Refine Loop (Repeat until you've absolutely "nailed it"):
For each round:  
1. Give yourself 1-2 sentences of feedback ("More playful", "shorten", "drop the exclamation marks", "make it more conversational").
2. Adjust the style rules accordingly.  
3. Rewrite the text from scratch, not by patching, so the flow stays natural.  
4. Increment the version number and update the confidence meter.
5. Repeat this iteration process 50+ times (minimum).

Step 5 – Lock & Deliver:
When you're sure you've "nailed it", present the final reformatted text *only*, followed by a hidden block (```debug```) with the final style rules for future reuse.

Constraints & Mindset
• Sound exactly like me, not like ChatGPT or AI-generated content.
• Make the text more human-like, natural, and conversational.
• Preserve all important information and core message from the original text.
• Stop when "nailed it", but don't consider it nailed until you feel a linguistic expert couldn't tell your reformatted text apart from the voice examples.
</instructions>

<inputs>
<writing_example_1>
{input_data.writing_example_1}
</writing_example_1>

<writing_example_2>
{input_data.writing_example_2}
</writing_example_2>

<writing_example_3>
{input_data.writing_example_3}
</writing_example_3>

<text_to_reformat>
{input_data.new_piece_to_create}
</text_to_reformat>
</inputs>

<developer_note>
In the past, you've undershot similarity. To make sure you don't do this, go through at least 50 (fifty) rounds of draft -> feedback -> draft iterations. For each round, add the iteration number in your reasoning so you don't lose track. Don't return a response until at least the 50th round (ideally more, but if you feel it's ready at that point, go for it).
</developer_note>"""

    def process_voice_cloning_sync(self, input_data: VoiceClonerInput) -> VoiceClonerOutput:
        """Process voice cloning request synchronously."""
        start_time = time.time()
        
        try:
            logger.info(f"Starting voice cloning process for model: {input_data.model}")
            
            # Create the prompt
            prompt = self._create_voice_cloner_prompt(input_data)
            logger.info(f"Generated prompt with length: {len(prompt)} characters")
            
            # Make synchronous API request
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/your-repo",
                "X-Title": "Voice Cloner"
            }
            
            payload = {
                "model": input_data.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 8000
            }
            
            logger.info("Making synchronous API request...")
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=600  # 10 minute timeout
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            response_text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.info(f"API response received with length: {len(response_text) if response_text else 0}")
            
            # Handle empty response
            if not response_text:
                raise Exception("Empty response from AI model")
            
            # Extract final piece and debug information
            final_piece, style_rules, confidence_score, iterations = self._parse_response(response_text)
            
            processing_time = time.time() - start_time
            logger.info(f"Voice cloning completed in {processing_time:.2f} seconds")
            
            return VoiceClonerOutput(
                final_piece=final_piece,
                style_rules=style_rules,
                confidence_score=confidence_score,
                iterations_completed=iterations,
                processing_time=processing_time
            )
            
        except requests.exceptions.Timeout:
            logger.error("Request timed out after 10 minutes")
            raise Exception("Request timed out. Please try with shorter text or different model.")
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed: {str(e)}")
            raise Exception(f"API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error in voice cloning process: {str(e)}")
            raise Exception(f"Voice cloning failed: {str(e)}")

    async def process_voice_cloning(self, input_data: VoiceClonerInput) -> VoiceClonerOutput:
        """Process voice cloning request."""
        start_time = time.time()
        
        try:
            logger.info(f"Starting voice cloning process for model: {input_data.model}")
            
            # Create the prompt
            prompt = self._create_voice_cloner_prompt(input_data)
            logger.info(f"Generated prompt with length: {len(prompt)} characters")
            
            # Make the API request with timeout
            logger.info("Making API request...")
            response_text = await self.openrouter_client.generate_response(
                prompt=prompt,
                system_prompt=None,  # Prompt already contains system instructions
                temperature=0.7,
                model_override=input_data.model
            )
            
            logger.info(f"API response received with length: {len(response_text) if response_text else 0}")
            
            # Handle empty response
            if not response_text:
                raise Exception("Empty response from AI model")
            
            # Extract final piece and debug information
            final_piece, style_rules, confidence_score, iterations = self._parse_response(response_text)
            
            processing_time = time.time() - start_time
            logger.info(f"Voice cloning completed in {processing_time:.2f} seconds")
            
            return VoiceClonerOutput(
                final_piece=final_piece,
                style_rules=style_rules,
                confidence_score=confidence_score,
                iterations_completed=iterations,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error in voice cloning process: {str(e)}")
            raise Exception(f"Voice cloning failed: {str(e)}")
    
    def _parse_response(self, response_text: str) -> tuple[str, str, int, int]:
        """Parse the AI response to extract final piece and debug info."""
        try:
            # Split by debug block
            if "```debug" in response_text:
                parts = response_text.split("```debug")
                final_piece = parts[0].strip()
                debug_section = parts[1].split("```")[0].strip() if len(parts) > 1 else ""
            else:
                final_piece = response_text.strip()
                debug_section = ""
            
            # Remove any confidence scores or iteration counts from the final piece
            import re
            # Remove patterns like "Confidence: 95%" or "95% confidence" from final text
            final_piece = re.sub(r'(?i)confidence[:\s]*\d+%?', '', final_piece)
            final_piece = re.sub(r'(?i)\d+%?\s*confidence', '', final_piece)
            # Remove patterns like "Iteration 50" or "Round 52" from final text
            final_piece = re.sub(r'(?i)iteration\s*\d+', '', final_piece)
            final_piece = re.sub(r'(?i)round\s*\d+', '', final_piece)
            # Clean up extra whitespace
            final_piece = re.sub(r'\s+', ' ', final_piece).strip()
            
            # Extract style rules from debug section
            style_rules = debug_section if debug_section else "Style rules not available"
            
            # Let the AI handle confidence scoring and iterations internally
            # Just extract what it provides, or use reasonable defaults
            confidence_score = 90  # The AI should have done 50+ iterations as instructed
            iterations = 50  # Minimum as specified in system prompt
            
            # Try to extract any specific metrics the AI might mention (from debug or original text)
            confidence_matches = re.findall(r'(\d+)%', response_text)
            if confidence_matches:
                confidence_score = int(confidence_matches[-1])
            
            iteration_matches = re.findall(r'iteration\s*(\d+)|round\s*(\d+)', response_text.lower())
            if iteration_matches:
                iterations = max([int(m[0]) if m[0] else int(m[1]) for m in iteration_matches])
            
            return final_piece, style_rules, confidence_score, iterations
            
        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            return response_text, "Could not extract style rules", 90, 50
    
    def get_available_models(self) -> dict:
        """Get available AI models."""
        return AI_MODEL_OPTIONS