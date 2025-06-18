import os
import json
import aiohttp
from aiohttp import ClientTimeout
from typing import Dict, Any, Optional, List, TypedDict
import asyncio
import ssl
import certifi
from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_PRIMARY_MODEL,
    SYSTEM_PROMPT
)

class SearchResponse(TypedDict):
    data: List[Dict[str, str]]

class ResearchResult(TypedDict):
    learnings: List[str]
    visited_urls: List[str]

class OpenRouterClient:
    def __init__(self):
        # OpenRouter configuration
        self.openrouter_api_key = OPENROUTER_API_KEY
        self.openrouter_base_url = OPENROUTER_BASE_URL
        self.primary_model = OPENROUTER_PRIMARY_MODEL
        
        # Nano-GPT configuration (from environment)
        self.nanogpt_api_key = os.getenv("NANOGPT_API_KEY")
        self.nanogpt_base_url = os.getenv("NANOGPT_BASE_URL", "https://nano-gpt.com/api/v1")
        
        # Warn if nano-gpt key is missing
        if not self.nanogpt_api_key:
            print("Warning: NANOGPT_API_KEY is not set. DMind models will not work.")
        
        # Backward compatibility - keep old attribute names
        self.api_key = self.openrouter_api_key
        self.base_url = self.openrouter_base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/your-repo",  # Replace with your actual repo
            "X-Title": "DDQ Research Pipeline",
            "Content-Type": "application/json"
        }
    
    def _get_provider_config(self, model: str) -> Dict[str, Any]:
        """Get provider-specific configuration based on model name."""
        if model.startswith("nanogpt/") or model.startswith("dmind/"):
            # Nano-GPT provider (handles both nanogpt/ and dmind/ prefixes)
            if model.startswith("nanogpt/"):
                actual_model = model.replace("nanogpt/", "", 1)  # Remove prefix for API call
            else:  # dmind/ prefix - keep the full name for nano-gpt API
                actual_model = model  # Keep full name including dmind/ prefix
            
            # Check if API key is available
            if not self.nanogpt_api_key:
                print(f"Error: NANOGPT_API_KEY not set but required for model {model}")
                return None
                
            return {
                "base_url": self.nanogpt_base_url,
                "headers": {
                    "Authorization": f"Bearer {self.nanogpt_api_key}",
                    "Content-Type": "application/json"
                },
                "model": actual_model,
                "provider": "nanogpt"
            }
        else:
            # OpenRouter provider (default)
            return {
                "base_url": self.openrouter_base_url,
                "headers": {
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/your-repo",
                    "X-Title": "DDQ Research Pipeline",
                    "Content-Type": "application/json"
                },
                "model": model,
                "provider": "openrouter"
            }

    async def _make_request(self, model: str, messages: list, temperature: float = 0.7) -> Optional[Dict[str, Any]]:
        """Make an asynchronous request to the appropriate API provider."""
        provider_config = self._get_provider_config(model)
        if provider_config is None:
            print(f"Cannot get provider config for model {model}")
            return None
            
        url = f"{provider_config['base_url']}/chat/completions"
        
        payload = {
            "model": provider_config["model"],
            "messages": messages,
            "temperature": temperature
        }
        
        # Dynamic timeout based on model - dmind models need more time for thinking
        if "dmind" in provider_config["model"].lower():
            request_timeout = ClientTimeout(total=600)  # 10 minutes for dmind models
            print(f"Using extended timeout (600s) for dmind model: {provider_config['model']}")
        else:
            request_timeout = ClientTimeout(total=300)  # 5 minutes for other models

        # Create SSL context with proper certificate verification
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
        except Exception as ssl_error:
            print(f"SSL context creation failed, using relaxed SSL verification: {ssl_error}")
            # Fallback: Create SSL context with relaxed verification for development
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(headers=provider_config["headers"], connector=connector) as session:
            # Retry logic for 503 Service Unavailable errors
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with session.post(url, json=payload, timeout=request_timeout) as response:
                        response.raise_for_status()
                        
                        return await response.json()
                except asyncio.TimeoutError:
                     print(f"Request timed out while connecting to {provider_config['provider']} API with {model}")
                     return None
                except aiohttp.ClientResponseError as e:
                    if e.status == 503 and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                        print(f"503 Service Unavailable for {model}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    print(f"HTTP Error making request to {provider_config['provider']} API with {model}: Status {e.status}, Message: {e.message}")
                    try:
                        # Read error body from the response text if available
                        error_body = str(e)
                        if hasattr(e, 'text') and e.text:
                            error_body = e.text
                        print(f"Error details: {error_body}")
                    except Exception as read_e:
                        print(f"Could not read error details: {read_e}")
                    return None
                except aiohttp.ClientError as e:
                    print(f"Client Error making request to {provider_config['provider']} API with {model}: {e}")
                    return None

    async def generate_response(self,
                         prompt: str, 
                         system_prompt: Optional[str] = None,
                         temperature: float = 0.7,
                         model_override: Optional[str] = None) -> Optional[str]:
        """Generate a response using the OpenRouter API with fallback, asynchronously.
        If model_override is provided, it uses that model directly, skipping primary/fallback.
        """
        messages = []
        system_prompt_to_use = system_prompt or SYSTEM_PROMPT
        messages.append({"role": "system", "content": system_prompt_to_use})
        messages.append({"role": "user", "content": prompt})
        
        response_data = None
        
        if model_override:
            # Use the specified override model with fallback
            provider_config = self._get_provider_config(model_override)
            print(f"Using model override: {model_override} via {provider_config['provider']}")
            response_data = await self._make_request(model_override, messages, temperature)
            
            # If override model fails, try fallback
            if not response_data and model_override != "openai/gpt-4o-mini":
                print(f"Model {model_override} failed, falling back to openai/gpt-4o-mini")
                response_data = await self._make_request("openai/gpt-4o-mini", messages, temperature)
        else:
            # Use primary model with fallback logic
            provider_config = self._get_provider_config(self.primary_model)
            print(f"Using primary model: {self.primary_model} via {provider_config['provider']}")
            response_data = await self._make_request(self.primary_model, messages, temperature)
            
            # If primary model fails, try fallback
            if not response_data and self.primary_model != "openai/gpt-4o-mini":
                print(f"Primary model {self.primary_model} failed, falling back to openai/gpt-4o-mini")
                response_data = await self._make_request("openai/gpt-4o-mini", messages, temperature)
        
        # Process the response (regardless of which model was used)
        if response_data and "choices" in response_data and response_data["choices"]:
            return response_data["choices"][0]["message"]["content"]
        
        # Log if response_data was received but didn't have expected content
        if response_data:
             print(f"Warning: Received response data but could not extract content. Data: {response_data}")
        
        return None

    async def analyze_ddq(self, ddq_content: str, system_prompt: str) -> Optional[str]:
        """Analyze a DDQ document and generate a research report, asynchronously."""
        structure_prompt = f"""Please analyze the following DDQ document and identify its structure and key sections:

{ddq_content}

Please provide a brief overview of the document's structure and main sections."""

        structure_analysis = await self.generate_response(structure_prompt, system_prompt)
        if not structure_analysis:
            structure_analysis = "Could not analyze document structure."
        
        analysis_prompt = f"""Based on the following DDQ document and its structure analysis, please generate a comprehensive due diligence report:

Document Structure Analysis:
{structure_analysis}

DDQ Content:
{ddq_content}

Please follow the Chain of Thought Framework and Task Formatting guidelines provided in the system prompt to create a detailed analysis."""

        return await self.generate_response(analysis_prompt, system_prompt)

    async def generate_serp_queries(self, query: str, num_queries: int = 3, learnings: Optional[List[str]] = None) -> List[Dict[str, str]]:
        prompt = f"""Given the following prompt from the user, generate a list of SERP queries to research the topic. Return a JSON object with a 'queries' array field containing {num_queries} queries (or less if the original prompt is clear). Each query object should have 'query' and 'research_goal' fields. Make sure each query is unique and not similar to each other: <prompt>{query}</prompt>"""

        if learnings:
            prompt += f"\n\nHere are some learnings from previous research, use them to generate more specific queries: {' '.join(learnings)}"

        response_text = await self.generate_response(prompt, SYSTEM_PROMPT)
        
        try:
            if response_text:
                data = json.loads(response_text)
                return data.get("queries", [])[:num_queries]
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for SERP queries: {e}")
            print(f"Raw response for SERP queries: {response_text}")
        
        return []

    async def process_serp_result(self, query: str, search_result: SearchResponse, num_learnings: int = 3, num_follow_up_questions: int = 3) -> Dict[str, List[str]]:
        contents = []
        for item in search_result["data"]:
            text = item.get("content") or item.get("description") or ""
            if text:
                contents.append(text[:25000])

        contents_str = "".join(f"<content>\n{content}\n</content>" for content in contents)

        prompt = (
            f"Given the following contents from a SERP search for the query <query>{query}</query>, "
            f"generate a list of learnings from the contents. Return a JSON object with 'learnings' "
            f"and 'followUpQuestions' keys with array of strings as values. Include up to {num_learnings} learnings and "
            f"{num_follow_up_questions} follow-up questions. The learnings should be unique, "
            "concise, and information-dense, including entities, metrics, numbers, and dates.\n\n"
            f"<contents>{contents_str}</contents>"
        )

        response_text = await self.generate_response(prompt, SYSTEM_PROMPT)
        
        try:
            if response_text:
                data = json.loads(response_text)
                return {
                    "learnings": data.get("learnings", [])[:num_learnings],
                    "followUpQuestions": data.get("followUpQuestions", [])[:num_follow_up_questions]
                }
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for SERP results: {e}")
            print(f"Raw response for SERP results: {response_text}")
        
        return {"learnings": [], "followUpQuestions": []}

    async def write_final_report(self, prompt: str, learnings: List[str], visited_urls: List[str]) -> str:
        learnings_string = "\n".join([f"<learning>\n{learning}\n</learning>" for learning in learnings])

        user_prompt = (
            f"Given the following prompt from the user, write a final report on the topic using "
            f"the learnings from research. Return a JSON object with a 'reportMarkdown' field "
            f"containing a detailed markdown report (aim for 3+ pages). Include ALL the learnings "
            f"from research:\n\n<prompt>{prompt}</prompt>\n\n"
            f"Here are all the learnings from research:\n\n<learnings>\n{learnings_string}\n</learnings>"
        )

        response_text = await self.generate_response(user_prompt, SYSTEM_PROMPT)
        
        try:
            if response_text:
                data = json.loads(response_text)
                report = data.get("reportMarkdown", "")
                urls_section = "\n\n## Sources\n\n" + "\n".join(
                    [f"- [{url}]({url})" for url in visited_urls]
                )
                return report + urls_section
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for final report: {e}")
            print(f"Raw response for final report: {response_text}")
        
        return "Error generating final report" 