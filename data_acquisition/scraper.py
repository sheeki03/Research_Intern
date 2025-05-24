import random
from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..utils import logger
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Browser, BrowserContext, TimeoutError

# ---- Data Models ----


@dataclass
class ScrapedContent:
    """Standardized scraped content format."""

    url: str
    html: str
    text: str
    status_code: int
    metadata: Dict[str, Any] = None


# ---- Scraper Interfaces ----


class Scraper(ABC):
    """Abstract base class for scrapers."""

    @abstractmethod
    async def setup(self):
        """Initialize the scraper resources."""
        pass

    @abstractmethod
    async def teardown(self):
        """Clean up the scraper resources."""
        pass

    @abstractmethod
    async def scrape(self, url: str, **kwargs) -> ScrapedContent:
        """Scrape a URL and return standardized content."""
        pass


class PlaywrightScraper:
    """Playwright-based scraper implementation."""

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
        user_agent: Optional[str] = None,
        timeout: int = 6000,
    ):
        self.headless = headless
        self.browser_type = browser_type
        self.user_agent = user_agent
        self.timeout = timeout
        self.browser = None
        self.context = None

    async def setup(self):
        """Initialize Playwright browser and context."""

        self.playwright = await async_playwright().start()

        browser_method = getattr(self.playwright, self.browser_type)

        self.browser = await browser_method.launch(
            headless=self.headless,
            # Anti-detection measures
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-window-activation",
                "--disable-focus-on-load",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-startup-window",
                "--window-position=0,0",
                "--disable-notifications",
                "--disable-extensions",
                "--mute-audio",
            ],
        )
        self.context = await self.setup_context(self.browser)

        logger.info(
            f"Playwright {self.browser_type} browser initialized in {'headless' if self.headless else 'headed'} mode"
        )

    async def setup_context(self, browser: Browser) -> BrowserContext:
        """
        Sets up and returns a BrowserContext with anti-detection measures.
        """
        # Common user agents
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        ]

        # Use random user agent if none provided
        selected_user_agent = self.user_agent or random.choice(self.user_agents)

        # Set up context with custom settings
        context = await browser.new_context(
            user_agent=selected_user_agent,
            accept_downloads=True,
            ignore_https_errors=True,
            has_touch=random.choice([True, False]),  # Random touch capability
            locale=random.choice(["en-US", "en-GB", "en-CA"]),  # Random locale
            timezone_id=random.choice(
                ["America/New_York", "Europe/London", "Asia/Tokyo"]
            ),  # Random timezone
            permissions=["geolocation", "notifications"],
            java_script_enabled=True,
        )

        # Set default timeout
        context.set_default_timeout(self.timeout)

        # Add anti-detection scripts
        await context.add_init_script("""
            // Override webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'es']
            });

            // Mock plugins array
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    return {
                        length: 5,
                        item: function(index) { return this[index]; },
                        refresh: function() {},
                        0: { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        1: { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Portable Document Format' },
                        2: { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                        3: { name: 'Widevine Content Decryption Module', filename: 'widevinecdmadapter.dll', description: 'Enables Widevine licenses for playback of HTML audio/video content.' }
                    };
                }
            });

            // Add chrome object
            window.chrome = {
                runtime: {
                    connect: () => {},
                    sendMessage: () => {}
                },
                webstore: {
                    onInstallStageChanged: {},
                    onDownloadProgress: {}
                },
                app: {
                    isInstalled: false,
                },
                csi: function(){},
                loadTimes: function(){}
            };

            // Override permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Prevent detection of shadow DOM manipulation
            (function() {
                const originalAttachShadow = Element.prototype.attachShadow;
                Element.prototype.attachShadow = function attachShadow(options) {
                    return originalAttachShadow.call(this, { ...options, mode: "open" });
                };
            })();

            // Add WebGL properties
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris Pro Graphics';
                }
                return getParameter.call(this, parameter);
            };
        """)

        return context

    async def teardown(self):
        """Clean up Playwright resources."""
        if self.browser:
            await self.browser.close()
        if hasattr(self, "playwright") and self.playwright:
            await self.playwright.stop()
        logger.info("Playwright resources cleaned up")

    async def scrape(self, url: str, **kwargs) -> ScrapedContent:
        """Scrape a URL using Playwright and return standardized content."""
        if not self.browser:
            await self.setup()

        try:
            page = await self.context.new_page()

            # Navigate to URL
            try:
                response = await page.goto(url, wait_until="networkidle")
            except TimeoutError:
                logger.warning(
                    "Networkidle timed out. Proceeding with partially loaded content."
                )
                response = None

            status_code = response.status if response else 0

            # Get HTML and text content
            title = await page.title()
            html = await page.content()

            # ------- MOST IMPORTANT COMMENT IN THE REPO -------
            # Extract only user-visible text content from the page
            # This excludes: hidden elements, navigation dropdowns, collapsed accordions,
            # inactive tabs, script/style content, SVG code, HTML comments, and metadata
            # Essentially captures what a human would see when viewing the page
            text = await page.evaluate("document.body.innerText")

            # Close the page
            await page.close()

            return ScrapedContent(
                url=url,
                html=html,
                text=text,
                status_code=status_code,
                metadata={
                    "title": title,
                    "headers": response.headers if response else {},
                },
            )

        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return ScrapedContent(
                url=url, html="", text="", status_code=0, metadata={"error": str(e)}
            )
