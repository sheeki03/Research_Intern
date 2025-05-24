import os
import json
import aiohttp
from aiohttp import ClientTimeout
from typing import Dict, Any, Optional, List, TypedDict
import asyncio
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
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self.primary_model = OPENROUTER_PRIMARY_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/your-repo",  # Replace with your actual repo
            "X-Title": "DDQ Research Pipeline",
            "Content-Type": "application/json"
        }

    async def _make_request(self, model: str, messages: list, temperature: float = 0.7) -> Optional[Dict[str, Any]]:
        """Make an asynchronous request to the OpenRouter API using aiohttp."""
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        
        request_timeout = ClientTimeout(total=300)

        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.post(url, json=payload, timeout=request_timeout) as response:
                    response.raise_for_status()
                    
                    return await response.json()
            except asyncio.TimeoutError:
                 print(f"Request timed out while connecting or reading from OpenRouter API with {model}")
                 return None
            except aiohttp.ClientResponseError as e:
                print(f"HTTP Error making request to OpenRouter API with {model}: Status {e.status}, Message: {e.message}, Headers: {e.headers}")
                try:
                    error_body = await e.read()
                    print(f"Error body: {error_body.decode()}")
                except Exception as read_e:
                    print(f"Could not read error body: {read_e}")
                return None
            except aiohttp.ClientError as e:
                print(f"Client Error making request to OpenRouter API with {model}: {e}")
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
            # Use the specified override model
            print(f"Using provided model override: {model_override}")
            response_data = await self._make_request(model_override, messages, temperature)
        else:
            # Use primary model with fallback logic
            print(f"Using primary model: {self.primary_model}")
            response_data = await self._make_request(self.primary_model, messages, temperature)
        
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