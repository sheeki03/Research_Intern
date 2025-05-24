from typing import Dict, Any, Optional, List
import aiohttp
import json
import redis
from urllib.parse import urlparse
import validators
from datetime import datetime
import os
import asyncio
import time

class FirecrawlClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        cache_ttl: int = 3600  # 1 hour cache
    ):
        actual_url_used = base_url or os.getenv("FIRECRAWL_API_URL", "http://localhost:3002")
        print(f"DEBUG: FirecrawlClient initializing with base_url: {actual_url_used}")
        self.base_url = actual_url_used
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.cache_ttl = cache_ttl
        self.redis_client = redis.from_url(redis_url) if redis_url else None

    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key for a URL."""
        return f"firecrawl:content:{url}"

    async def _get_from_cache(self, url: str) -> Optional[Dict[str, Any]]:
        """Get cached content for a URL."""
        if not self.redis_client:
            return None
        
        cached = self.redis_client.get(self._get_cache_key(url))
        if cached:
            # Ensure cached data is valid JSON before loading
            try:
                loaded_data = json.loads(cached)
                # Basic check: ensure it's a dictionary as expected
                if isinstance(loaded_data, dict):
                     return loaded_data
                else:
                    print(f"Warning: Invalid non-dict data found in cache for {url}. Ignoring cache.")
                    # Optionally delete the invalid cache entry
                    # self.redis_client.delete(self._get_cache_key(url))
                    return None
            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON found in cache for {url}. Ignoring cache.")
                # Optionally delete the invalid cache entry
                # self.redis_client.delete(self._get_cache_key(url))
                return None
        return None

    async def _save_to_cache(self, url: str, content: Dict[str, Any]) -> None:
        """Save content to cache."""
        if not self.redis_client:
            return
        
        try:
             # Ensure content is serializable before caching
             json_content = json.dumps(content)
             self.redis_client.setex(
                self._get_cache_key(url),
                self.cache_ttl,
                json_content
             )
        except TypeError as e:
             print(f"Error: Failed to serialize content for caching URL {url}. Error: {e}")
        except Exception as e: # Catch other potential redis errors
             print(f"Error: Failed to save to cache for URL {url}. Error: {e}")

    def validate_url(self, url: str) -> bool:
        """Validate if a URL is well-formed and allowed."""
        if not validators.url(url):
            return False
        
        parsed = urlparse(url)
        # Add any additional validation rules here
        # For example, only allow certain domains or protocols
        return parsed.scheme in ['http', 'https']

    async def _poll_for_markdown(self, status_url: str, initial_delay: float = 1.0, max_attempts: int = 10, backoff_factor: float = 1.5, timeout: float = 60.0) -> Dict[str, Optional[str]]:
        """Polls the Firecrawl status URL for completed job and returns a dict with markdown and html if available."""
        start_time = time.monotonic()
        attempts = 0
        delay = initial_delay
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
        }

        async with aiohttp.ClientSession() as session:
            while attempts < max_attempts:
                if time.monotonic() - start_time > timeout:
                    raise TimeoutError(f"Polling timed out after {timeout} seconds for URL: {status_url}")

                print(f"DEBUG: Polling attempt {attempts + 1}/{max_attempts} for {status_url} after {delay:.2f}s delay...")
                await asyncio.sleep(delay)

                try:
                    # Use a timeout for the individual poll request
                    async with session.get(status_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status != 200:
                            error_text_poll = await response.text()
                            print(f"Warning: Polling {status_url} returned status {response.status}. Body: {error_text_poll}. Retrying...")
                        else:
                            poll_result = await response.json()
                            print(f"DEBUG: Poll response: {poll_result}")

                            # Check for job completion and content (adjust based on actual status API response structure)
                            job_status = poll_result.get("status", "").lower() # Hypothetical status field

                            # Check for actual data first (most reliable indicator)
                            if poll_result.get("data") and isinstance(poll_result["data"], dict):
                                data_block = poll_result["data"]
                                markdown_content = data_block.get("markdown")
                                html_content_poll = data_block.get("html")
                                if markdown_content is not None:
                                    print(f"DEBUG: Polling successful. Found markdown (and possibly HTML) for {status_url}")
                                    return {"markdown": markdown_content, "html": html_content_poll}
                            # Check specific status indicators if data isn't present yet
                            elif job_status == "completed": # Explicit completed status
                                 # Completed but no markdown? Raise error.
                                 raise ValueError(f"Polling job completed for {status_url} but markdown content missing in response: {poll_result}")
                            elif job_status == "failed": # Explicit failed status
                                raise ValueError(f"Polling job failed for {status_url}. Response: {poll_result}")
                            elif job_status in ["pending", "active", "running", ""]: # Assume empty status means pending/active
                                print(f"DEBUG: Job for {status_url} status: '{job_status}'. Continuing poll.")
                                # Continue polling
                            else:
                                # Unknown status or structure, treat as potentially ongoing unless error indicators exist
                                print(f"Warning: Unknown status '{job_status}' or structure in poll response for {status_url}: {poll_result}")
                                # Could add checks here for other error patterns if needed

                except asyncio.TimeoutError: # Catch timeout for the specific request
                     print(f"Warning: Timeout during individual poll request for {status_url}. Retrying...")
                except aiohttp.ClientError as e:
                    print(f"Warning: Connection error during polling {status_url}: {e}. Retrying...")
                except json.JSONDecodeError as e:
                     print(f"Warning: Failed to decode JSON from poll response for {status_url}: {e}. Retrying...")
                except Exception as e:
                     print(f"Error processing poll response for {status_url}: {e}. Failing job.") # Fail on unexpected errors
                     raise ValueError(f"Error processing poll response: {e}")

                attempts += 1
                delay *= backoff_factor
                delay = min(delay, 10.0) # Cap delay to avoid excessive waits

        raise TimeoutError(f"Polling failed after {max_attempts} attempts for URL: {status_url}")

    async def scrape_url(self, url: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Scrape content from a URL using Firecrawl. Handles sync/async responses.
        
        Args:
            url: The URL to scrape
            force_refresh: If True, ignore cache and fetch fresh content
            
        Returns:
            Dict containing standardized scraped content ('data.content') and metadata,
            or an error field if scraping failed.
        """
        if not self.validate_url(url):
            # Return error structure for invalid URL
            return {
                'data': {'content': ''},
                'error': f"Invalid URL provided: {url}",
                'metadata': {"url": url, "scraped_at": datetime.utcnow().isoformat()}
            }

        # Check cache first
        if not force_refresh:
            cached = await self._get_from_cache(url)
            if cached:
                # Ensure cached item has the expected keys, otherwise treat as miss
                if 'data' in cached and 'metadata' in cached:
                    print(f"DEBUG: Cache hit for {url}")
                    return cached
                else:
                    print(f"Warning: Cache item for {url} has unexpected structure. Ignoring cache.")

        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
        }
        # Ensure scrape requests markdown format
        scrape_payload = {"url": url, "formats": ["markdown", "html"]}
        scrape_endpoint = f"{self.base_url}/v1/scrape"
        final_result = {} # Initialize final_result

        try:
            async with aiohttp.ClientSession() as session:
                print(f"DEBUG: POSTing to {scrape_endpoint} for URL: {url} with payload: {scrape_payload}")
                # Add timeout to the main scrape request
                async with session.post(
                    scrape_endpoint,
                    json=scrape_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30) # e.g., 30 second timeout for initial request
                ) as response:

                    if response.status != 200:
                        error_text = await response.text()
                        try:
                            error_json = json.loads(error_text)
                            error_message = error_json.get("error", error_text)
                        except json.JSONDecodeError:
                            error_message = error_text
                        raise Exception(f"Firecrawl API error ({response.status}): {error_message}")

                    initial_result = await response.json()
                    print(f"DEBUG: Initial response for {url}: {initial_result}")

                    content_found = None
                    metadata = {} # Reset metadata, get from final result

                    # --- Check for Synchronous Response ---
                    if initial_result.get("data") and isinstance(initial_result["data"], dict):
                        data_block = initial_result["data"]
                        markdown_content = data_block.get("markdown")
                        html_content_sync = data_block.get("html") # Get HTML if present
                        
                        if markdown_content is not None:
                            print(f"DEBUG: Found synchronous markdown for {url}")
                            content_found = markdown_content
                            # Attempt to get metadata from within data block if present
                            metadata = data_block.get("metadata", initial_result.get("metadata", {}))
                            # Add HTML content to the structure if found
                            if html_content_sync:
                                # This part needs careful structuring for the final_result
                                # For now, let's assume we'll handle it in final_result construction
                                pass 
                        else:
                            print(f"DEBUG: Synchronous 'data' block present but no 'markdown' content for {url}")

                    # --- Check for Asynchronous Response ---
                    # Ensure 'data' is explicitly missing or not a dict for async path
                    elif initial_result.get("success") and initial_result.get("id") and initial_result.get("url") and \
                         (not initial_result.get("data") or not isinstance(initial_result["data"], dict)):
                        status_url = initial_result["url"] # The 'url' in the response is the status polling URL
                        print(f"DEBUG: Detected async job for {url}. Starting polling at {status_url}")
                        try:
                            # Modify _poll_for_markdown to potentially return a dict with markdown and html
                            polled_data = await self._poll_for_markdown(status_url) 
                            content_found = polled_data.get("markdown")
                            html_content_async = polled_data.get("html")
                            # Polling returns content, use initial response metadata if available
                            metadata = initial_result.get("metadata", {})
                        except (TimeoutError, ValueError) as poll_e:
                             print(f"Error during polling for {url}: {poll_e}")
                             # Set error message for final result construction
                             final_result['error'] = f"Polling failed: {poll_e}"
                             # Keep content_found as None

                    # --- Construct Final Result ---
                    if content_found is not None:
                         final_result = {
                            'data': {
                                'content': content_found, # Standardize to 'content' key for markdown
                                'html_content': html_content_sync if initial_result.get("data") else html_content_async # Pass HTML through
                            },
                            'metadata': metadata
                         }
                         final_result.pop('error', None)
                    else:
                        # If neither sync nor async polling succeeded or produced content
                        # Use error from polling if set, otherwise generic failure
                        error_msg = final_result.get('error', 'Failed to retrieve content')
                        if not final_result.get('error'): # Avoid overwriting specific polling error
                             print(f"Warning: Failed to get content for {url} via sync or async polling. Initial response: {initial_result}")
                        final_result = {
                             'data': {'content': ''},
                             'error': error_msg,
                             'metadata': initial_result.get("metadata", {}) # Preserve metadata if possible
                         }

        except asyncio.TimeoutError: # Catch timeout for the initial POST request
            error_msg = f"Timeout connecting to or receiving initial response from Firecrawl for {url}"
            print(f"ERROR: {error_msg}")
            final_result = {'data': {'content': ''}, 'error': error_msg, 'metadata': {"url": url}}
        except aiohttp.ClientError as e:
            error_msg = f"Failed to connect to Firecrawl: {str(e)}"
            print(f"ERROR: {error_msg}")
            final_result = {'data': {'content': ''}, 'error': error_msg, 'metadata': {"url": url}}
        except Exception as e:
            error_msg = f"Unexpected error during scrape process for {url}: {str(e)}"
            print(f"ERROR: {error_msg}")
            final_result = {'data': {'content': ''}, 'error': error_msg, 'metadata': {"url": url}}

        # Add standard metadata (timestamp, original URL) to whatever result we have
        if 'metadata' not in final_result: final_result['metadata'] = {}
        final_result["metadata"]["scraped_at"] = datetime.utcnow().isoformat()
        final_result["metadata"]["url"] = url # Ensure original URL is always present

        # Cache the final structured result (including potential errors)
        await self._save_to_cache(url, final_result)
        print(f"DEBUG: Final result being returned for {url}: {final_result}") # Log final return value
        return final_result

    async def scrape_multiple_urls(
        self,
        urls: List[str],
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Scrape multiple URLs, now using the enhanced scrape_url."""
        if not urls:
            return []

        valid_urls = [url for url in urls if self.validate_url(url)]
        invalid_url_results = [
             {
                "url": url, "error": "Invalid URL", "success": False,
                "data": {"content": ""}, "metadata": {"url": url}
             } for url in urls if url not in valid_urls
        ]

        if not valid_urls:
             return invalid_url_results

        # Create tasks for valid URLs
        tasks = [self.scrape_url(url, force_refresh=force_refresh) for url in valid_urls]
        results = await asyncio.gather(*tasks)

        # Process results, adding 'success' flag based on 'error' field
        processed_results = []
        for result in results:
             # Result structure from scrape_url now includes 'error' key on failure
             is_success = 'error' not in result or not result['error']
             processed_results.append({
                 **result,
                 "success": is_success,
                 # Ensure 'url' is top-level for consistency if scrape_url didn't add it somehow
                 "url": result.get("metadata", {}).get("url", "unknown_url_in_processing")
             })

        return processed_results + invalid_url_results # Combine valid and invalid results 