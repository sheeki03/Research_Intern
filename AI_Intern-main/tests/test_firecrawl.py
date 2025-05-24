# Simple test script
import os
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("FIRECRAWL_API_KEY")
if not api_key:
    print("ERROR: FIRECRAWL_API_KEY environment variable not set.")
    exit(1)

app = FirecrawlApp(api_key=api_key)
url_to_test = "https://blog.mexc.com/what-is-hyperliquid/"

print(f"Attempting to scrape: {url_to_test}")
result = None
try:
    # Use run_in_executor for async compatibility if needed, but direct call is fine for testing
    result = app.scrape_url(url=url_to_test, params={'pageOptions': {'onlyMainContent': True}}, timeout=60000) # Explicit timeout, basic options
    print(f"--- Scrape Result for {url_to_test} ---")
    print(f"Type: {type(result)}")
    # Try to print as dict if it's an object with dict() or model_dump()
    if hasattr(result, 'model_dump'):
        print(result.model_dump(exclude_none=True))
    elif hasattr(result, 'dict'):
        print(result.dict(exclude_none=True))
    else:
        print(result)
    print("-------------------------------------")
except Exception as e:
    print(f"--- SCRAPE FAILED for {url_to_test} ---")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Details: {e}")
    print("-------------------------------------")

if result is None:
    print("Script finished, but scrape result was None (likely due to an error).")
else:
    print("Script finished.")