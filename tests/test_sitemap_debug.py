import asyncio
import sys
sys.path.append('.')
from src.core.scanner_utils import discover_sitemap_urls, fetch_robots_txt, fetch_sitemap_content
import logging

logging.basicConfig(level=logging.INFO)

async def test_loopfi():
    print('Testing sitemap discovery for docs.loopfi.xyz...')
    
    # Test robots.txt first
    print('\n1. Checking robots.txt...')
    robots = await fetch_robots_txt('https://docs.loopfi.xyz/')
    if robots:
        print(f'Found robots.txt: {robots[:500]}...')
    else:
        print('No robots.txt found')
    
    # Test direct sitemap access
    print('\n2. Checking direct sitemap access...')
    sitemap_content = await fetch_sitemap_content('https://docs.loopfi.xyz/sitemap.xml')
    if sitemap_content:
        print(f'Found sitemap.xml: {len(sitemap_content)} chars')
        print(f'Preview: {sitemap_content[:500]}...')
    else:
        print('No sitemap.xml found at standard location')
    
    # Test full discovery
    print('\n3. Running full discovery...')
    urls = await discover_sitemap_urls('https://docs.loopfi.xyz/')
    print(f'Discovered {len(urls)} URLs')
    if urls:
        print('First 10 URLs:')
        for url in urls[:10]:
            print(f'  - {url}')

if __name__ == "__main__":
    asyncio.run(test_loopfi()) 