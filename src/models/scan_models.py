"""
Pydantic models for the site scanning feature.
"""
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional

class ScanRequest(BaseModel):
    """
    Request model for initiating a site scan to discover URLs from sitemaps.
    """
    site_url: str = Field(
        ..., 
        description="The URL of the site to scan. Can be a base domain (e.g., 'example.com') or a full URL (e.g., 'https://example.com/somepath').",
        examples=["example.com", "https://www.python.org"]
    )

class ScanResponse(BaseModel):
    """
    Response model for the site scan operation.
    Includes the list of discovered URLs or an error message if the scan failed.
    """
    site_url: str = Field(description="The original site URL that was scanned.")
    urls: Optional[List[str]] = Field(default=None, description="A list of unique, absolute page URLs discovered from the site's sitemaps. None if an error occurred or no URLs found.")
    message: Optional[str] = Field(default=None, description="An optional message, e.g., indicating success, no sitemaps found, or providing error details.")
    error: Optional[str] = Field(default=None, description="An error message if the scanning process failed at a high level. Specific parsing/fetching issues might be in logs.")

    # Add an __init__.py to src/models if it becomes a package 