"""
Utilities for scanning websites, including fetching robots.txt and sitemaps.
"""
import httpx
from typing import Optional, List, Set, Tuple
from urllib.parse import urljoin, urlparse
import logging
import xml.etree.ElementTree as ET
import asyncio

# It's good practice to configure logging at the application level.
# For this module, we'll get a logger instance.
# Ensure your main application configures logging (e.g., basicConfig).
logger = logging.getLogger(__name__)

MAX_SITEMAP_DEPTH = 5 # To prevent infinite loops with misconfigured sitemaps
MAX_SITEMAPS_TO_PROCESS = 50 # To cap processing time for very large sites

async def fetch_robots_txt(domain_or_url: str) -> Optional[str]:
    """
    Fetches the robots.txt file for a given domain or base URL.
    If a full URL is provided (e.g., 'http://example.com'), it uses that scheme.
    If only a domain is provided (e.g., 'example.com'), it tries HTTPS first, then HTTP.

    Args:
        domain_or_url: The domain name (e.g., "example.com") 
                       or a base URL (e.g., "http://example.com").

    Returns:
        The content of robots.txt as a string, 
        or None if fetching fails or robots.txt is not found.
    """
    parsed_url = urlparse(domain_or_url)
    
    urls_to_try = []
    # Ensure domain_or_url is treated correctly if it's just a domain like "example.com"
    # urlparse might put "example.com" in path if no scheme, or netloc if "http://example.com"
    
    if parsed_url.scheme and parsed_url.netloc:
        # Full URL provided like "http://example.com" or "http://example.com/some/path"
        # We only care about the scheme and netloc for robots.txt
        base_for_robots = f"{parsed_url.scheme}://{parsed_url.netloc}"
        urls_to_try.append(urljoin(base_for_robots, "robots.txt"))
    elif not parsed_url.scheme and (parsed_url.netloc or parsed_url.path):
        # Likely a domain like "example.com" (parsed_url.path will be "example.com")
        # or "example.com:8000" (parsed_url.netloc might be empty, path is "example.com:8000")
        # The robust way is to treat domain_or_url as the authority if no scheme.
        # We clean it up to ensure it's just the domain/host.
        host_part = parsed_url.netloc or parsed_url.path
        if '/' in host_part: # If domain_or_url was "example.com/something"
            host_part = host_part.split('/')[0]

        urls_to_try.append(f"https://{host_part.rstrip('/')}/robots.txt")
        urls_to_try.append(f"http://{host_part.rstrip('/')}/robots.txt")
    else:
        logger.error(f"Invalid domain or URL format provided: {domain_or_url}")
        return None

    # Using a shared client for potential multiple requests (though only one successful here)
    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
        for url in urls_to_try:
            logger.debug(f"Attempting to fetch robots.txt from: {url}")
            try:
                response = await client.get(url)
                response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
                logger.info(f"Successfully fetched robots.txt from {url} (status {response.status_code})")
                return response.text
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error {e.response.status_code} fetching {url}. Response: {e.response.text[:200]}")
                # If it's a 404 and there are other URLs to try (i.e., trying https then http), continue
                if e.response.status_code == 404 and url != urls_to_try[-1]:
                    continue
                # For 404 on the last attempt, or other HTTP errors, this attempt failed.
                # If it's the last url in the list, we'll fall through and return None.
                # Otherwise, the loop continues to the next url.
                # For this function, if one fails (not 404 on first try), we return None from that path.
                if e.response.status_code == 404: # Explicitly means not found
                    return None # As per success criteria for 404
                # Any other HTTP error is also a failure for this specific URL.
                # If it's the last URL to try, this will lead to returning None after the loop.
            except httpx.RequestError as e:
                logger.error(f"Request error fetching {url}: {str(e)}")
                # If there are other URLs to try, continue
                if url != urls_to_try[-1]:
                    continue
                # For request error on the last attempt, this attempt failed.
                # This will lead to returning None after the loop.
            # If we are here after an error, and it wasn't a "continue" case:
            # If it's not the last URL, we try the next one.
            # If it *is* the last URL and we had an error that wasn't a 404 on https, we'll fall through.
            # Let's be more explicit: if an attempt fails and it's not a "404 on first scheme" case,
            # and there are no more schemes/URLs to try, then this path is exhausted.

    logger.warning(f"Failed to fetch robots.txt for {domain_or_url} after trying: {urls_to_try}")
    return None

def parse_sitemap_urls_from_robots(robots_txt_content: str) -> list[str]:
    """
    Parses robots.txt content to find sitemap URLs.

    Args:
        robots_txt_content: The content of the robots.txt file as a string.

    Returns:
        A list of sitemap URLs found in the robots.txt content. 
        Returns an empty list if no sitemap URLs are found or content is None.
    """
    sitemap_urls = []
    if not robots_txt_content:
        return sitemap_urls

    for line in robots_txt_content.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            try:
                # Sitemap: http://www.example.com/sitemap.xml
                #         ^~~~~~~~~^ <--- 8 characters for "sitemap:"
                sitemap_url = line[8:].strip()
                if sitemap_url: # Ensure it's not just "Sitemap: "
                    sitemap_urls.append(sitemap_url)
            except IndexError:
                # Line was "sitemap:" but nothing after it, or too short
                logger.warning(f"Found 'Sitemap:' directive with no URL: {line}")
                continue
    
    logger.info(f"Found {len(sitemap_urls)} sitemap URLs in robots.txt: {sitemap_urls}")
    return sitemap_urls

async def fetch_sitemap_content(sitemap_url: str) -> Optional[str]:
    """
    Fetches the content of a sitemap file from a given URL.
    Handles potential GZip compression automatically via httpx.

    Args:
        sitemap_url: The URL of the sitemap file (e.g., http://example.com/sitemap.xml 
                     or http://example.com/sitemap.xml.gz).

    Returns:
        The sitemap content as a string, or None if fetching or decompression fails.
    """
    if not sitemap_url:
        logger.warning("fetch_sitemap_content called with empty or None URL")
        return None

    logger.info(f"Attempting to fetch sitemap content from: {sitemap_url}")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client: # Increased timeout for potentially larger files
            response = await client.get(sitemap_url)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx
            
            # httpx handles content decoding (like gzip) automatically based on Content-Encoding header.
            # response.text will give the decoded text.
            sitemap_content = response.text
            logger.info(f"Successfully fetched and decoded sitemap from {sitemap_url}. Length: {len(sitemap_content)} chars.")
            # Basic check for XML structure, as sitemaps should be XML
            if not sitemap_content.strip().startswith(("<?xml", "<sitemapindex", "<urlset")):
                logger.warning(f"Content from {sitemap_url} does not look like XML. Preview: {sitemap_content[:200]}")
                # Depending on strictness, one might return None here, but for now, we return what we got.
            return sitemap_content
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error {e.response.status_code} fetching sitemap {sitemap_url}. Response: {e.response.text[:200]}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error fetching sitemap {sitemap_url}: {str(e)}")
        return None
    except Exception as e:
        # Catch any other unexpected errors during processing, e.g. text decoding issues not caught by httpx
        logger.error(f"Unexpected error processing sitemap {sitemap_url}: {str(e)}")
        return None

def parse_xml_sitemap(xml_content: str, sitemap_url: str, target_domain: str) -> Tuple[List[str], List[str]]:
    """
    Parses XML sitemap content (either a sitemap index or a URL set).

    Args:
        xml_content: The XML content of the sitemap as a string.
        sitemap_url: The URL from which this sitemap was fetched (for resolving relative URLs).
        target_domain: The domain we are interested in (e.g., "example.com"). 
                       Only URLs from this domain will be returned.

    Returns:
        A tuple containing two lists: 
        (page_urls: List[str], further_sitemap_urls: List[str])
        - page_urls: Unique, absolute URLs of web pages from the target domain.
        - further_sitemap_urls: Unique, absolute URLs of other sitemaps from the target domain 
                                (if the input was a sitemap index).
    """
    page_urls_set: Set[str] = set()
    further_sitemap_urls_set: Set[str] = set()

    if not xml_content or not target_domain:
        logger.warning("parse_xml_sitemap called with empty xml_content or target_domain.")
        return [], []

    try:
        # Remove default namespace for easier parsing, a common issue with sitemap XML
        # Sitemaps often use xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        # This makes find/findall require {namespace}tag, which is cumbersome.
        # A common way to handle this is to remove the namespace if known.
        # More robustly, one might parse with namespaces, but for simplicity for common sitemap format:
        xml_content = xml_content.replace('xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"', '', 1)
        # Also for image sitemaps or other extensions, though we primarily care about <loc>
        xml_content = xml_content.replace('xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"', '', 1)
        # Add others if they become problematic: xmlns:video, xmlns:news, etc.

        root = ET.fromstring(xml_content)
        parsed_sitemap_url_base = urlparse(sitemap_url)

        # Check if it's a sitemap index file or a urlset
        if root.tag.endswith('sitemapindex'):
            logger.debug(f"Parsing sitemap index: {sitemap_url}")
            for sitemap_node in root.findall('sitemap'): # Path relative to root
                loc_node = sitemap_node.find('loc')
                if loc_node is not None and loc_node.text:
                    found_sitemap_url = urljoin(sitemap_url, loc_node.text.strip())
                    parsed_found_url = urlparse(found_sitemap_url)
                    if parsed_found_url.netloc == target_domain:
                        further_sitemap_urls_set.add(found_sitemap_url)
                    else:
                        logger.debug(f"Skipping sitemap URL (wrong domain): {found_sitemap_url} (target: {target_domain})")
        elif root.tag.endswith('urlset'):
            logger.debug(f"Parsing urlset: {sitemap_url}")
            for url_node in root.findall('url'): # Path relative to root
                loc_node = url_node.find('loc')
                if loc_node is not None and loc_node.text:
                    page_url = urljoin(sitemap_url, loc_node.text.strip())
                    parsed_page_url = urlparse(page_url)
                    if parsed_page_url.netloc == target_domain:
                        page_urls_set.add(page_url)
                    else:
                        logger.debug(f"Skipping page URL (wrong domain): {page_url} (target: {target_domain})")
        else:
            logger.warning(f"Unknown root tag in sitemap XML: {root.tag} from {sitemap_url}")
            return [], []

    except ET.ParseError as e:
        logger.error(f"XML ParseError for sitemap {sitemap_url}: {e}. Content preview: {xml_content[:500]}")
        return [], []
    except Exception as e:
        logger.error(f"Unexpected error parsing XML sitemap {sitemap_url}: {str(e)}")
        return [], []

    final_page_urls = sorted(list(page_urls_set))
    final_further_sitemaps = sorted(list(further_sitemap_urls_set))
    logger.info(f"Parsed from {sitemap_url}: {len(final_page_urls)} page URLs, {len(final_further_sitemaps)} further sitemap URLs for domain {target_domain}.")
    return final_page_urls, final_further_sitemaps

async def discover_sitemap_urls(initial_url: str) -> List[str]:
    """
    Facade function to discover all unique page URLs from a website's sitemaps.
    It starts by checking robots.txt, then common sitemap locations, 
    and recursively processes sitemap indexes.

    Args:
        initial_url: The base URL of the website (e.g., "http://example.com", "example.com").

    Returns:
        A sorted list of unique, absolute page URLs belonging to the target domain found in sitemaps.
        Returns an empty list if no sitemaps are found or no relevant URLs are extracted.
    """
    if not initial_url:
        logger.warning("discover_sitemap_urls called with no initial_url")
        return []

    parsed_initial_url = urlparse(initial_url)
    if not parsed_initial_url.scheme:
        # If no scheme, assume https, then try http if robots.txt fetch fails with https.
        # For simplicity in the facade, let fetch_robots_txt handle scheme guessing for robots.txt.
        # For the target_domain and base_url_for_domain, we'll establish one.
        # Try to construct a base for domain extraction
        temp_url_for_domain = f"https://{initial_url.split('/')[0]}" 
        parsed_temp_url = urlparse(temp_url_for_domain)
        if not parsed_temp_url.netloc:
            logger.error(f"Could not determine a valid domain from initial_url: {initial_url}")
            return []
        target_domain = parsed_temp_url.netloc
        # Use https as the preferred scheme for constructing sitemap URLs if not found in robots.txt
        base_url_for_domain = f"https://{target_domain}"
    else:
        target_domain = parsed_initial_url.netloc
        base_url_for_domain = f"{parsed_initial_url.scheme}://{target_domain}"
    
    logger.info(f"Starting sitemap discovery for domain: {target_domain} (base: {base_url_for_domain})")

    all_discovered_page_urls: Set[str] = set()
    sitemaps_to_process_queue: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()
    processed_sitemap_urls: Set[str] = set()
    sitemaps_processed_count = 0

    # 1. Try to get sitemap URLs from robots.txt
    robots_txt_content = await fetch_robots_txt(initial_url) # initial_url can be domain or full url
    sitemap_urls_from_robots: List[str] = []
    if robots_txt_content:
        sitemap_urls_from_robots = parse_sitemap_urls_from_robots(robots_txt_content)
        for s_url in sitemap_urls_from_robots:
            # Ensure these are absolute and potentially normalized against the base_url_for_domain
            # However, sitemaps in robots.txt should ideally be absolute.
            # We will add them to queue and let the processing logic handle normalization if needed or filtering.
            if urlparse(s_url).netloc == target_domain or not urlparse(s_url).netloc: # accept relative or same-domain
                 await sitemaps_to_process_queue.put((urljoin(base_url_for_domain, s_url), 0))
            else:
                logger.debug(f"Skipping sitemap from robots.txt (domain mismatch): {s_url}")

    # 2. If no sitemaps from robots.txt, try common locations like /sitemap.xml
    if not sitemap_urls_from_robots: # or sitemaps_to_process_queue.empty() after filtering
        common_sitemap_url = urljoin(base_url_for_domain, "/sitemap.xml")
        logger.info(f"No sitemaps in robots.txt (or all filtered out). Trying common location: {common_sitemap_url}")
        await sitemaps_to_process_queue.put((common_sitemap_url, 0))

    # 3. Process the sitemap queue
    while not sitemaps_to_process_queue.empty() and sitemaps_processed_count < MAX_SITEMAPS_TO_PROCESS:
        sitemap_url_to_fetch, current_depth = await sitemaps_to_process_queue.get()
        sitemaps_to_process_queue.task_done()

        if sitemap_url_to_fetch in processed_sitemap_urls:
            logger.debug(f"Skipping already processed sitemap: {sitemap_url_to_fetch}")
            continue
        
        if current_depth > MAX_SITEMAP_DEPTH:
            logger.warning(f"Reached max sitemap depth ({MAX_SITEMAP_DEPTH}) for {sitemap_url_to_fetch}. Stopping this path.")
            continue

        processed_sitemap_urls.add(sitemap_url_to_fetch)
        sitemaps_processed_count += 1
        logger.info(f"Processing sitemap ({sitemaps_processed_count}/{MAX_SITEMAPS_TO_PROCESS}, depth {current_depth}): {sitemap_url_to_fetch}")

        sitemap_content = await fetch_sitemap_content(sitemap_url_to_fetch)
        if sitemap_content:
            # The sitemap_url_to_fetch is the authoritative base for URLs within this sitemap content
            # target_domain is used for filtering
            page_urls, further_sitemap_urls = parse_xml_sitemap(sitemap_content, sitemap_url_to_fetch, target_domain)
            
            for page_url in page_urls:
                all_discovered_page_urls.add(page_url) # parse_xml_sitemap already ensures they are for target_domain and absolute
            
            for further_s_url in further_sitemap_urls:
                if further_s_url not in processed_sitemap_urls:
                    # further_s_url from parse_xml_sitemap should be absolute and for target_domain
                    await sitemaps_to_process_queue.put((further_s_url, current_depth + 1))
    
    if sitemaps_processed_count >= MAX_SITEMAPS_TO_PROCESS:
        logger.warning(f"Stopped processing sitemaps after reaching MAX_SITEMAPS_TO_PROCESS ({MAX_SITEMAPS_TO_PROCESS}).")

    final_url_list = sorted(list(all_discovered_page_urls))
    logger.info(f"Discovered {len(final_url_list)} unique page URLs for {target_domain}.")
    return final_url_list

# Example usage (for testing purposes, normally called from elsewhere)
if __name__ == '__main__':
    import asyncio

    async def main_test():
        # Configure basic logging for the test
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        
        # Test cases
        # Google should have one
        content_google = await fetch_robots_txt("google.com")
        if content_google:
            logger.info("Google robots.txt (first 200 chars):\n" + content_google[:200])
        else:
            logger.error("Failed to fetch Google robots.txt")

        # A non-existent domain
        content_nx = await fetch_robots_txt("nonexistentdomain123abc.com")
        if content_nx is None:
            logger.info("Correctly failed to fetch from nonexistentdomain123abc.com")
        else:
            logger.error("Incorrectly got content from nonexistentdomain123abc.com")

        # A site that might 404 on robots.txt (e.g., a small personal site or a deliberately configured one)
        # Using a known site that returns 404 or similar for robots.txt is hard,
        # let's assume a general case where it might not exist.
        # For this test, we'll use a domain that redirects http to https and has robots.txt
        content_http_redirect = await fetch_robots_txt("http://example.com") # should find at https://example.com/robots.txt
        if content_http_redirect:
            logger.info("example.com (via http) robots.txt (first 200 chars):\n" + content_http_redirect[:200])
        else:
            logger.error("Failed to fetch example.com (via http) robots.txt")
            
        content_https = await fetch_robots_txt("https://www.python.org")
        if content_https:
            logger.info("python.org robots.txt (first 200 chars):\n" + content_https[:200])
        else:
            logger.error("Failed to fetch python.org robots.txt")

        # Test cases for parse_sitemap_urls_from_robots
        logger.info("\n--- Testing parse_sitemap_urls_from_robots ---")
        sample_robots_1 = """
User-agent: *
Disallow: /private/
Sitemap: http://example.com/sitemap.xml
Sitemap: https://example.com/sitemap_index.xml
Allow: /
"""
        sitemaps_1 = parse_sitemap_urls_from_robots(sample_robots_1)
        logger.info(f"Parsed sitemaps from sample_robots_1: {sitemaps_1}")
        assert "http://example.com/sitemap.xml" in sitemaps_1
        assert "https://example.com/sitemap_index.xml" in sitemaps_1

        sample_robots_2 = """
User-agent: BadBot
Disallow: /
# No sitemap here
"""
        sitemaps_2 = parse_sitemap_urls_from_robots(sample_robots_2)
        logger.info(f"Parsed sitemaps from sample_robots_2: {sitemaps_2}")
        assert len(sitemaps_2) == 0

        sample_robots_3 = "Sitemap:    http://anothersite.com/sitemap.xml   "
        sitemaps_3 = parse_sitemap_urls_from_robots(sample_robots_3)
        logger.info(f"Parsed sitemaps from sample_robots_3: {sitemaps_3}")
        assert "http://anothersite.com/sitemap.xml" in sitemaps_3
        
        sample_robots_4_empty_directive = "Sitemap: "
        sitemaps_4 = parse_sitemap_urls_from_robots(sample_robots_4_empty_directive)
        logger.info(f"Parsed sitemaps from sample_robots_4_empty_directive: {sitemaps_4}")
        assert len(sitemaps_4) == 0

        sitemaps_empty_content = parse_sitemap_urls_from_robots("")
        logger.info(f"Parsed sitemaps from empty string: {sitemaps_empty_content}")
        assert len(sitemaps_empty_content) == 0
        
        sitemaps_none_content = parse_sitemap_urls_from_robots(None)
        logger.info(f"Parsed sitemaps from None: {sitemaps_none_content}")
        assert len(sitemaps_none_content) == 0

        if content_google:
            logger.info("\n--- Parsing Google's robots.txt ---")
            google_sitemaps = parse_sitemap_urls_from_robots(content_google)
            logger.info(f"Sitemaps found in Google's robots.txt: {google_sitemaps}")
        
        if content_https: # python.org robots.txt
            logger.info("\n--- Parsing Python.org's robots.txt ---")
            python_sitemaps = parse_sitemap_urls_from_robots(content_https)
            logger.info(f"Sitemaps found in Python.org's robots.txt: {python_sitemaps}")

        # Test cases for fetch_sitemap_content
        logger.info("\n--- Testing fetch_sitemap_content ---")
        # Test with a known, accessible sitemap (e.g., from python.org if it has one listed and accessible)
        # From python.org robots.txt: Sitemap: https://www.python.org/sitemap.xml
        python_sitemap_url = "https://www.python.org/sitemap.xml"
        sitemap_content_python = await fetch_sitemap_content(python_sitemap_url)
        if sitemap_content_python:
            logger.info(f"Successfully fetched Python.org sitemap. First 300 chars:\n{sitemap_content_python[:300]}")
            assert "<urlset" in sitemap_content_python or "<sitemapindex" in sitemap_content_python
        else:
            logger.error(f"Failed to fetch sitemap from {python_sitemap_url}")

        # Test with a known gzipped sitemap. Example: https://www.google.com/sitemap.xml (often a sitemap index)
        # Google's main sitemap is often an index and might be gzipped or redirect.
        # httpx should handle this.
        google_sitemap_url = "https://www.google.com/sitemap.xml"
        sitemap_content_google = await fetch_sitemap_content(google_sitemap_url)
        if sitemap_content_google:
            logger.info(f"Successfully fetched Google sitemap. First 300 chars:\n{sitemap_content_google[:300]}")
            assert "<sitemapindex" in sitemap_content_google or "<urlset" in sitemap_content_google
        else:
            logger.error(f"Failed to fetch sitemap from {google_sitemap_url}")

        # Test with a non-existent sitemap URL
        non_existent_sitemap_url = "http://example.com/nonexistentsitemap.xml"
        sitemap_content_non_existent = await fetch_sitemap_content(non_existent_sitemap_url)
        if sitemap_content_non_existent is None:
            logger.info(f"Correctly failed to fetch non-existent sitemap from {non_existent_sitemap_url}")
        else:
            logger.error(f"Incorrectly fetched content from non-existent sitemap {non_existent_sitemap_url}")
            
        # Test with an invalid URL format (should be caught by httpx or return None early)
        invalid_sitemap_url = "htp://not_a_valid_url_at_all"
        sitemap_content_invalid = await fetch_sitemap_content(invalid_sitemap_url)
        if sitemap_content_invalid is None:
            logger.info(f"Correctly handled invalid sitemap URL: {invalid_sitemap_url}")
        else:
            logger.error(f"Incorrectly processed invalid sitemap URL: {invalid_sitemap_url}")
        
        sitemap_content_empty_url = await fetch_sitemap_content("")
        if sitemap_content_empty_url is None:
            logger.info(f"Correctly handled empty sitemap URL.")
        else:
            logger.error(f"Incorrectly processed empty sitemap URL.")

        # Test cases for parse_xml_sitemap
        logger.info("\n--- Testing parse_xml_sitemap ---")
        target_domain_example = "example.com"

        # 1. Test with a sitemap index XML
        sitemap_index_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <sitemap>
      <loc>http://example.com/sitemap1.xml</loc>
      <lastmod>2023-01-01</lastmod>
   </sitemap>
   <sitemap>
      <loc>https://example.com/sitemap2.xml.gz</loc>
   </sitemap>
   <sitemap>
      <loc>http://anotherdomain.com/sitemap_other.xml</loc> <!-- Should be ignored -->
   </sitemap>
   <sitemap>
      <loc>/sitemap_relative.xml</loc> <!-- Should be resolved -->
   </sitemap>
</sitemapindex>'''
        pages1, further_sitemaps1 = parse_xml_sitemap(sitemap_index_xml, f"http://{target_domain_example}/main_sitemap_index.xml", target_domain_example)
        logger.info(f"Sitemap Index Test 1 - Pages: {pages1}, Further Sitemaps: {further_sitemaps1}")
        assert len(pages1) == 0
        assert len(further_sitemaps1) == 3
        assert f"http://{target_domain_example}/sitemap1.xml" in further_sitemaps1
        assert f"https://{target_domain_example}/sitemap2.xml.gz" in further_sitemaps1
        assert f"http://{target_domain_example}/sitemap_relative.xml" in further_sitemaps1
        assert f"http://anotherdomain.com/sitemap_other.xml" not in further_sitemaps1 # Check exclusion

        # 2. Test with a URL set XML
        urlset_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>http://example.com/page1.html</loc>
      <lastmod>2023-01-01</lastmod>
      <changefreq>monthly</changefreq>
      <priority>0.8</priority>
   </url>
   <url>
      <loc>https://example.com/page2.html</loc>
   </url>
   <url>
      <loc>http://sub.example.com/page3.html</loc> <!-- Should be ignored if target_domain is example.com -->
   </url>
   <url>
      <loc>/relative_page.html</loc> <!-- Should be resolved -->
   </url>
</urlset>'''
        pages2, further_sitemaps2 = parse_xml_sitemap(urlset_xml, f"http://{target_domain_example}/sitemap_pages.xml", target_domain_example)
        logger.info(f"URL Set Test 1 - Pages: {pages2}, Further Sitemaps: {further_sitemaps2}")
        assert len(further_sitemaps2) == 0
        assert len(pages2) == 3
        assert f"http://{target_domain_example}/page1.html" in pages2
        assert f"https://{target_domain_example}/page2.html" in pages2 # Assumes example.com is canonical for https too
        assert f"http://{target_domain_example}/relative_page.html" in pages2
        assert f"http://sub.example.com/page3.html" not in pages2
        
        # 3. Test with malformed XML
        malformed_xml = "<sitemapindex><sitemap><loc>http://example.com/sitemap1.xml</sitemap></sitemapindex>"
        pages3, further_sitemaps3 = parse_xml_sitemap(malformed_xml, f"http://{target_domain_example}/malformed.xml", target_domain_example)
        logger.info(f"Malformed XML Test - Pages: {pages3}, Further Sitemaps: {further_sitemaps3}")
        assert len(pages3) == 0
        assert len(further_sitemaps3) == 0 # Should fail gracefully

        # 4. Test with unknown root tag
        unknown_root_xml = "<randomtag><item>text</item></randomtag>"
        pages4, further_sitemaps4 = parse_xml_sitemap(unknown_root_xml, f"http://{target_domain_example}/unknown.xml", target_domain_example)
        logger.info(f"Unknown Root XML Test - Pages: {pages4}, Further Sitemaps: {further_sitemaps4}")
        assert len(pages4) == 0
        assert len(further_sitemaps4) == 0

        # 5. Test with empty content
        pages5, further_sitemaps5 = parse_xml_sitemap("", f"http://{target_domain_example}/empty.xml", target_domain_example)
        logger.info(f"Empty XML Test - Pages: {pages5}, Further Sitemaps: {further_sitemaps5}")
        assert len(pages5) == 0
        assert len(further_sitemaps5) == 0
        
        # 6. Test with content that becomes empty after namespace stripping
        namespace_only_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</sitemapindex>''' # Effectively empty after stripping if not handled carefully by fromstring if it expects children
        pages6, further_sitemaps6 = parse_xml_sitemap(namespace_only_xml, f"http://{target_domain_example}/ns_only.xml", target_domain_example)
        logger.info(f"Namespace Only XML Test - Pages: {pages6}, Further Sitemaps: {further_sitemaps6}")
        assert len(pages6) == 0
        assert len(further_sitemaps6) == 0

        # Test cases for discover_sitemap_urls (Facade function)
        logger.info("\n--- Testing discover_sitemap_urls ---")

        # Mocking the network calls for discover_sitemap_urls is complex in this simple test block.
        # For a real test, you'd use a library like `pytest-asyncio` and `respx` or `aioresponses`.
        # Here, we'll try with live URLs, understanding they might change or fail.

        # Test 1: A site expected to have sitemaps (e.g., python.org)
        logger.info("\n--- discover_sitemap_urls: python.org ---")
        python_org_urls = await discover_sitemap_urls("python.org")
        if python_org_urls:
            logger.info(f"Found {len(python_org_urls)} URLs on python.org. First 5: {python_org_urls[:5]}")
            # Basic check: all URLs should be for python.org
            for u in python_org_urls[:5]: assert "python.org" in urlparse(u).netloc
        else:
            logger.warning("Could not discover sitemap URLs for python.org (might be network or actual site change)")

        # Test 2: A site that might not have an easily discoverable sitemap or is small
        # Using example.com - it has robots.txt but typically no sitemap listed there or at /sitemap.xml (it's simple)
        logger.info("\n--- discover_sitemap_urls: example.com ---")
        example_com_urls = await discover_sitemap_urls("example.com")
        if not example_com_urls:
            logger.info("Correctly found no sitemap URLs for example.com (or it truly has none discoverable by this method).")
        else:
            logger.warning(f"Found {len(example_com_urls)} URLs for example.com, which was unexpected: {example_com_urls[:5]}")

        # Test 3: Non-existent domain
        logger.info("\n--- discover_sitemap_urls: nonexistentsite12345.com ---")
        non_existent_urls = await discover_sitemap_urls("nonexistentsite12345.com")
        if not non_existent_urls:
            logger.info("Correctly found no URLs for a non-existent domain.")
        else:
            logger.error(f"Incorrectly found URLs for non-existent domain: {non_existent_urls}")
            
        # Test 4: URL with path, ensure it uses the domain
        logger.info("\n--- discover_sitemap_urls: https://www.djangoproject.com/start/ ---")
        django_urls = await discover_sitemap_urls("https://www.djangoproject.com/start/")
        if django_urls:
            logger.info(f"Found {len(django_urls)} URLs on djangoproject.com. First 5: {django_urls[:5]}")
            for u in django_urls[:5]: assert "djangoproject.com" in urlparse(u).netloc
        else:
            logger.warning("Could not discover sitemap URLs for djangoproject.com")

    asyncio.run(main_test()) 