from typing import List, Dict, TypedDict, Optional, Any
from dataclasses import dataclass
import asyncio
import openai
from .data_acquisition.services import search_service
from .ai.providers import trim_prompt, get_client_response
import sys
from pathlib import Path
# Import from the web_research directory instead of root
from .prompt import system_prompt
import json
from src.config import SYSTEM_PROMPT
# Use simple OpenAI client instead of complex OpenRouterClient to avoid import issues
import openai
from openai import OpenAI


class SearchResponse(TypedDict):
    data: List[Dict[str, str]]


class ResearchResult(TypedDict):
    learnings: List[str]
    visited_urls: List[str]


@dataclass
class SerpQuery:
    query: str
    research_goal: str


async def generate_serp_queries(
    query: str,
    client: openai.OpenAI,
    model: str,
    num_queries: int = 3,
    learnings: Optional[List[str]] = None,
) -> List[SerpQuery]:
    """Generate SERP queries based on user input and previous learnings."""

    prompt = f"""Given the following prompt from the user, generate a list of SERP queries to research the topic. Return a JSON object with a 'queries' array field containing {num_queries} queries (or less if the original prompt is clear). Each query object should have 'query' and 'research_goal' fields. Make sure each query is unique and not similar to each other: <prompt>{query}</prompt>"""

    if learnings:
        prompt += f"\n\nHere are some learnings from previous research, use them to generate more specific queries: {' '.join(learnings)}"

    response = await get_client_response(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        queries = response.get("queries", [])
        return [SerpQuery(**q) for q in queries][:num_queries]
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response}")
        return []


async def process_serp_result(
    query: str,
    search_result: SearchResponse,
    client: openai.OpenAI,
    model: str,
    num_learnings: int = 3,
    num_follow_up_questions: int = 3,
) -> Dict[str, List[str]]:
    """Process search results to extract learnings and follow-up questions."""

    contents = []
    for item in search_result["data"]:
        text = item.get("content") or item.get("description") or ""
        if text:
            contents.append(trim_prompt(text, 25_000))

    # Create the contents string separately
    contents_str = "".join(f"<content>\n{content}\n</content>" for content in contents)

    prompt = (
        f"Given the following contents from a SERP search for the query <query>{query}</query>, "
        f"generate a list of learnings from the contents. Return a JSON object with 'learnings' "
        f"and 'followUpQuestions' keys with array of strings as values. Include up to {num_learnings} learnings and "
        f"{num_follow_up_questions} follow-up questions. The learnings should be unique, "
        "concise, and information-dense, including entities, metrics, numbers, and dates.\n\n"
        f"<contents>{contents_str}</contents>"
    )

    response = await get_client_response(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        return {
            "learnings": response.get("learnings", [])[:num_learnings],
            "followUpQuestions": response.get("followUpQuestions", [])[
                :num_follow_up_questions
            ],
        }
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response}")
        return {"learnings": [], "followUpQuestions": []}


async def write_final_report(
    prompt: str,
    learnings: List[str],
    visited_urls: List[str],
    client: openai.OpenAI,
    model: str,
) -> str:
    """Generate final report based on all research learnings."""

    learnings_string = trim_prompt(
        "\n".join([f"<learning>\n{learning}\n</learning>" for learning in learnings]),
        150_000,
    )

    user_prompt = (
        f"Given the following prompt from the user, write a final report on the topic using "
        f"the learnings from research. Return a JSON object with a 'reportMarkdown' field "
        f"containing a detailed markdown report (aim for 3+ pages). Include ALL the learnings "
        f"from research:\n\n<prompt>{prompt}</prompt>\n\n"
        f"Here are all the learnings from research:\n\n<learnings>\n{learnings_string}\n</learnings>"
    )

    response = await get_client_response(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        report = response.get("reportMarkdown", "")

        # Append sources
        urls_section = "\n\n## Sources\n\n" + "\n".join(
            [f"- {url}" for url in visited_urls]
        )
        return report + urls_section
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response}")
        return "Error generating report"


async def deep_research(
    query: str,
    breadth: int,
    depth: int,
    concurrency: int,
    client: openai.OpenAI,
    model: str,
    learnings: List[str] = None,
    visited_urls: List[str] = None,
) -> ResearchResult:
    """
    Main research function that recursively explores a topic.

    Args:
        query: Research query/topic
        breadth: Number of parallel searches to perform
        depth: How many levels deep to research
        learnings: Previous learnings to build upon
        visited_urls: Previously visited URLs
    """
    learnings = learnings or []
    visited_urls = visited_urls or []

    # Generate search queries
    serp_queries = await generate_serp_queries(
        query=query,
        client=client,
        model=model,
        num_queries=breadth,
        learnings=learnings,
    )

    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(concurrency)

    async def process_query(serp_query: SerpQuery) -> ResearchResult:
        async with semaphore:
            try:
                # Search for content
                result = await search_service.search(serp_query.query, limit=5)

                # Collect new URLs
                new_urls = [
                    item.get("url") for item in result["data"] if item.get("url")
                ]

                # Calculate new breadth and depth for next iteration
                new_breadth = max(1, breadth // 2)
                new_depth = depth - 1

                # Process the search results
                new_learnings = await process_serp_result(
                    query=serp_query.query,
                    search_result=result,
                    num_follow_up_questions=new_breadth,
                    client=client,
                    model=model,
                )

                all_learnings = learnings + new_learnings["learnings"]
                all_urls = visited_urls + new_urls

                # If we have more depth to go, continue research
                if new_depth > 0:
                    print(
                        f"Researching deeper, breadth: {new_breadth}, depth: {new_depth}"
                    )

                    next_query = f"""
                    Previous research goal: {serp_query.research_goal}
                    Follow-up research directions: {" ".join(new_learnings["followUpQuestions"])}
                    """.strip()

                    return await deep_research(
                        query=next_query,
                        breadth=new_breadth,
                        depth=new_depth,
                        concurrency=concurrency,
                        learnings=all_learnings,
                        visited_urls=all_urls,
                        client=client,
                        model=model,
                    )

                return {"learnings": all_learnings, "visited_urls": all_urls}

            except Exception as e:
                if "Timeout" in str(e):
                    print(f"Timeout error running query: {serp_query.query}: {e}")
                else:
                    print(f"Error running query: {serp_query.query}: {e}")
                return {"learnings": [], "visited_urls": []}

    # Process all queries concurrently
    results = await asyncio.gather(*[process_query(query) for query in serp_queries])

    # Combine all results
    all_learnings = list(
        set(learning for result in results for learning in result["learnings"])
    )

    all_urls = list(set(url for result in results for url in result["visited_urls"]))

    return {"learnings": all_learnings, "visited_urls": all_urls}


async def process_search_results(results: List[Dict[str, Any]], client: OpenAI) -> Dict[str, Any]:
    """Process search results and extract insights."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(results)}
    ]
    
    # ... rest of the function ...


async def generate_final_report(insights: Dict[str, Any], client: OpenAI) -> str:
    """Generate a final research report."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(insights)}
    ]
    
    # ... rest of the function ...
