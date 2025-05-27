import asyncio
import sys
sys.path.append('.')
from src.core.scanner_utils import discover_sitemap_urls
import logging

# Set logging to DEBUG to see all details
logging.basicConfig(level=logging.DEBUG)

async def test_simple():
    print('Testing sitemap discovery for docs.loopfi.xyz...')
    urls = await discover_sitemap_urls('https://docs.loopfi.xyz/')
    print(f'Discovered {len(urls)} URLs')
    if urls:
        print('URLs found:')
        for i, url in enumerate(urls[:20]):  # Show first 20
            print(f'  {i+1}. {url}')
        if len(urls) > 20:
            print(f'  ... and {len(urls) - 20} more URLs')
    else:
        print('No URLs found')

if __name__ == "__main__":
    asyncio.run(test_simple()) 