from enum import Enum
from typing import Dict, Optional, Any, List, TypedDict
import os
import json
import asyncio
from firecrawl import FirecrawlApp
from firecrawl.firecrawl import ScrapeOptions  # type: ignore
from .manager import SearchAndScrapeManager
from ..utils import logger


class SearchServiceType(Enum):
    """Supported search service types."""

    FIRECRAWL = "firecrawl"
    PLAYWRIGHT_DDGS = "playwright_ddgs"


class SearchResponse(TypedDict):
    data: List[Dict[str, str]]


class SearchService:
    """Unified search service that supports multiple implementations."""

    def __init__(self, service_type: Optional[str] = None):
        """Initialize the appropriate search service.

        Args:
            service_type: The type of search service to use. Defaults to env var or playwright_ddgs.
        """
        # Determine which service to use
        if service_type is None:
            service_type = os.environ.get("DEFAULT_SCRAPER", "playwright_ddgs")

        self.service_type = service_type

        # Initialize the appropriate service
        if service_type == SearchServiceType.FIRECRAWL.value:
            self.firecrawl = Firecrawl(
                api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
                api_url=os.environ.get("FIRECRAWL_BASE_URL"),
            )
            self.manager = None
        else:
            self.firecrawl = None
            self.manager = SearchAndScrapeManager()
            # Initialize resources asynchronously later
            self._initialized = False

    async def ensure_initialized(self):
        """Ensure the service is initialized."""
        if self.manager and not getattr(self, "_initialized", False):
            await self.manager.setup()
            self._initialized = True

    async def cleanup(self):
        """Clean up resources."""
        if self.manager and getattr(self, "_initialized", False):
            await self.manager.teardown()
            self._initialized = False

    async def search(
        self, query: str, limit: int = 5, save_content: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """Search using the configured service.

        Returns data in a format compatible with the Firecrawl response format.
        """
        await self.ensure_initialized()

        logger.info(
            "action=search.start service=%s query=\"%s\" limit=%d",
            self.service_type,
            query.replace("\n", " ")[:120],
            limit,
        )

        try:
            if self.service_type == SearchServiceType.FIRECRAWL.value:
                response = await self.firecrawl.search(query, limit=limit, **kwargs)

                # Convert Pydantic model to plain dict if returned by SDK
                if not isinstance(response, (dict, list)):
                    if hasattr(response, "model_dump"):
                        response = response.model_dump(exclude_none=True)
                    elif hasattr(response, "dict"):
                        response = response.dict(exclude_none=True)
            else:
                scraped_data = await self.manager.search_and_scrape(
                    query, num_results=limit, scrape_all=True, **kwargs
                )

                # Format the response to match Firecrawl format
                formatted_data = []
                for result in scraped_data["search_results"]:
                    item = {
                        "url": result.url,
                        "title": result.title,
                        "content": "",  # Default empty content
                    }

                    # Add content if we scraped it
                    if result.url in scraped_data["scraped_contents"]:
                        scraped = scraped_data["scraped_contents"][result.url]
                        item["content"] = scraped.text

                    formatted_data.append(item)

                response = {"data": formatted_data}

            if save_content:
                # Create the directory if it doesn't exist
                os.makedirs("scraped_content", exist_ok=True)

                # Save each result as a separate JSON file
                for item in response.get("data", []):
                    # Create a safe filename from the first 50 chars of the title
                    title = item.get("title", "untitled")
                    safe_filename = "".join(
                        c for c in title[:50] if c.isalnum() or c in " ._-"
                    ).strip()
                    safe_filename = safe_filename.replace(" ", "_")

                    # Save the content to a JSON file
                    with open(
                        f"scraped_content/{safe_filename}.json", "w", encoding="utf-8"
                    ) as f:
                        json.dump(item, f, ensure_ascii=False, indent=2)

            logger.info(
                "action=search.success service=%s items=%d",
                self.service_type,
                len(response.get("data", [])),
            )

            return response

        except Exception as e:
            logger.exception("action=search.error service=%s query=%s", self.service_type, query)
            return {"data": []}


class Firecrawl:
    """Simple wrapper for Firecrawl SDK."""

    def __init__(self, api_key: str = "", api_url: Optional[str] = None):
        self.app = FirecrawlApp(api_key=api_key, api_url=api_url)

    async def search(
        self, query: str, timeout: int = 15000, limit: int = 5
    ) -> SearchResponse:
        """Search using Firecrawl SDK in a thread pool to keep it async."""
        try:
            # Ask Firecrawl to also scrape page content in Markdown format so we can
            # feed it to the LLM.  The `formats=["markdown"]` option tells Firecrawl
            # to include the page text for every SERP result.
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.app.search(
                    query=query,
                    limit=limit,
                    timeout=timeout,
                    scrape_options=ScrapeOptions(formats=["markdown"]),
                ),
            )

            # Handle the response format from the SDK
            if hasattr(response, "data"):
                # Firecrawl SDK SearchResponse object (pydantic). Extract .data list.
                raw_items = response.data  # type: ignore[attr-defined]

                formatted_data = []
                for item in raw_items:
                    if isinstance(item, dict):
                        # Ensure there is a 'content' key so downstream code can use it
                        if "content" not in item:
                            # Prefer markdown if present, otherwise fall back to snippet/description
                            if item.get("markdown"):
                                item["content"] = item["markdown"]
                            elif item.get("description"):
                                item["content"] = item["description"]
                        formatted_data.append(item)
                    else:
                        formatted_data.append(
                            {
                                "url": getattr(item, "url", ""),
                                # Use markdown field if available; fall back to content attribute
                                "content": getattr(item, "markdown", "")
                                or getattr(item, "content", ""),
                                "title": getattr(item, "title", "")
                                or getattr(item, "metadata", {}).get("title", ""),
                            }
                        )

                return {"data": formatted_data}

            elif isinstance(response, list):
                # Response is a list of results
                formatted_data = []
                for item in response:
                    if isinstance(item, dict):
                        # Ensure there is a 'content' key so downstream code can use it
                        if "content" not in item:
                            # Prefer markdown if present, otherwise fall back to snippet/description
                            if item.get("markdown"):
                                item["content"] = item["markdown"]
                            elif item.get("description"):
                                item["content"] = item["description"]
                        formatted_data.append(item)
                    else:
                        formatted_data.append(
                            {
                                "url": getattr(item, "url", ""),
                                # Use markdown field if available; fall back to content attribute
                                "content": getattr(item, "markdown", "")
                                or getattr(item, "content", ""),
                                "title": getattr(item, "title", "")
                                or getattr(item, "metadata", {}).get("title", ""),
                            }
                        )
                return {"data": formatted_data}
            else:
                logger.warning(
                    "Unexpected response format from Firecrawl: %s", type(response)
                )
                return {"data": []}

        except Exception as e:
            print(f"Error searching with Firecrawl: {e}")
            print(
                f"Response type: {type(response) if 'response' in locals() else 'N/A'}"
            )
            return {"data": []}


# Initialize a global instance with the default settings
search_service = SearchService(
    service_type=os.getenv("DEFAULT_SCRAPER", "playwright_ddgs")
)
