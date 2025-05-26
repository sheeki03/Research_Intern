"""
DocSend Client for AI Research Agent.
Handles DocSend deck processing with OCR text extraction.
"""

import asyncio
import io
import os
import time
from typing import Dict, Any, Optional

import platform
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from PIL import Image
import pytesseract

class DocSendClient:
    """Client for processing DocSend presentations with OCR."""
    
    def __init__(self, tesseract_cmd: str = None, preferred_browser: str = 'auto'):
        """
        Initialize DocSend client with optional Tesseract path and browser preference.
        
        Args:
            tesseract_cmd: Path to tesseract executable (auto-detected if None)
            preferred_browser: 'chrome', 'firefox', 'edge', or 'auto' for automatic detection
        """
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        self.preferred_browser = preferred_browser.lower()
        self.os_type = platform.system().lower()
        
        # Suppress logs
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        os.environ['PYTHONWARNINGS'] = 'ignore'
    
    def _get_user_agent(self) -> str:
        """Get appropriate user agent string based on OS."""
        if self.os_type == 'darwin':  # macOS
            return 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        elif self.os_type == 'windows':
            return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        else:  # Linux and others
            return 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    
    def _init_chrome(self):
        """Initialize Chrome browser with enhanced stealth capabilities and container support."""
        try:
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument(f'--user-agent={self._get_user_agent()}')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            
            # Container-specific arguments
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument("--disable-features=TranslateUI")
            chrome_options.add_argument("--disable-ipc-flooding-protection")
            chrome_options.add_argument("--remote-debugging-port=9222")
            
            # Enhanced stealth arguments to avoid bot detection
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-client-side-phishing-detection")
            chrome_options.add_argument("--disable-sync")
            chrome_options.add_argument("--metrics-recording-only")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--safebrowsing-disable-auto-update")
            chrome_options.add_argument("--password-store=basic")
            chrome_options.add_argument("--use-mock-keychain")
            
            # Additional preferences to appear more human-like
            prefs = {
                "profile.default_content_setting_values": {
                    "notifications": 2,  # Block notifications
                    "geolocation": 2,    # Block location sharing
                },
                "profile.managed_default_content_settings": {
                    "images": 1  # Allow images
                },
                "profile.default_content_settings": {
                    "popups": 0  # Allow popups (some sites need this)
                },
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            # Set Chrome/Chromium binary path if available in environment or system
            chrome_bin = os.environ.get('CHROME_BIN')
            if chrome_bin and os.path.exists(chrome_bin):
                chrome_options.binary_location = chrome_bin
                print(f"Using Chrome binary from environment: {chrome_bin}")
            else:
                # Try to find Chrome or Chromium binary
                import shutil
                for binary in ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']:
                    binary_path = shutil.which(binary)
                    if binary_path:
                        chrome_options.binary_location = binary_path
                        print(f"Found Chrome/Chromium binary: {binary_path}")
                        break
            
            # Try to use system chromedriver first, then fallback to ChromeDriverManager
            service = None
            try:
                # Check for system chromedriver from environment or PATH
                chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
                if chromedriver_path and os.path.exists(chromedriver_path):
                    service = ChromeService(chromedriver_path)
                    print(f"Using chromedriver from environment: {chromedriver_path}")
                else:
                    # Try system chromedriver in PATH
                    import shutil
                    system_driver = shutil.which('chromedriver')
                    if system_driver:
                        service = ChromeService(system_driver)
                        print(f"Using system chromedriver: {system_driver}")
                    else:
                        service = ChromeService()
                        print("Using default chromedriver service")
                
                browser = webdriver.Chrome(service=service, options=chrome_options)
                print("✅ Chrome/Chromium browser initialized successfully")
            except Exception as e:
                # Fallback to ChromeDriverManager
                print(f"System chromedriver failed ({str(e)}), using ChromeDriverManager...")
                try:
            service = ChromeService(ChromeDriverManager().install())
            browser = webdriver.Chrome(service=service, options=chrome_options)
                    print("✅ Using ChromeDriverManager chromedriver")
                except Exception as e2:
                    raise WebDriverException(f"Both system and managed chromedriver failed. System: {str(e)}, Managed: {str(e2)}")
            
            # Execute JavaScript to remove webdriver property and add human-like properties
            browser.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                // Add some human-like properties
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                // Override the permissions API if it exists
                if (window.navigator.permissions && window.navigator.permissions.query) {
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                }
                
                // Add realistic screen properties
                Object.defineProperty(screen, 'availWidth', {
                    get: () => 1920,
                });
                Object.defineProperty(screen, 'availHeight', {
                    get: () => 1080,
                });
            """)
            
            return browser
        except Exception as e:
            raise WebDriverException(f"Failed to initialize Chrome: {str(e)}")
    
    def _init_firefox(self):
        """Initialize Firefox browser."""
        try:
            firefox_options = FirefoxOptions()
            firefox_options.add_argument("--headless")
            firefox_options.set_preference("general.useragent.override", self._get_user_agent())
            firefox_options.set_preference("dom.webdriver.enabled", False)
            firefox_options.set_preference("useAutomationExtension", False)
            firefox_options.set_preference("media.volume_scale", "0.0")
            
            service = FirefoxService(GeckoDriverManager().install())
            return webdriver.Firefox(service=service, options=firefox_options)
        except Exception as e:
            raise WebDriverException(f"Failed to initialize Firefox: {str(e)}")
    
    def _init_edge(self):
        """Initialize Edge browser."""
        try:
            edge_options = EdgeOptions()
            edge_options.add_argument("--headless=new")
            edge_options.add_argument(f'--user-agent={self._get_user_agent()}')
            edge_options.add_argument('--no-sandbox')
            edge_options.add_argument("--disable-gpu")
            edge_options.add_argument('--log-level=3')
            edge_options.add_argument("--window-size=1200,900")
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_argument("--disable-extensions")
            edge_options.add_argument("--disable-blink-features=AutomationControlled")
            
            service = EdgeService(EdgeChromiumDriverManager().install())
            return webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            raise WebDriverException(f"Failed to initialize Edge: {str(e)}")
    
    def _detect_available_browsers(self) -> list:
        """Detect which browsers are available on the system without initializing them."""
        available = []
        
        # Check for Chrome/Chromium binary
        try:
            import shutil
            chrome_binaries = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']
            if any(shutil.which(binary) for binary in chrome_binaries):
            available.append('chrome')
        except:
            pass
        
        # Check for Firefox binary
        try:
            import shutil
            if shutil.which('firefox') or shutil.which('firefox-esr'):
            available.append('firefox')
        except:
            pass
        
        # Check for Edge binary (less common in containers)
        try:
            import shutil
            if shutil.which('microsoft-edge') or shutil.which('msedge'):
            available.append('edge')
        except:
            pass
        
        return available
    
    def _init_browser(self):
        """Initialize and return a configured browser instance with robust fallback support."""
        # Prioritize Chrome for container environments
        browsers_to_try = ['chrome']  # Start with Chrome only for better reliability
        
        # Only add other browsers if specifically requested or Chrome fails
        if self.preferred_browser == 'firefox':
            browsers_to_try = ['firefox', 'chrome']
        elif self.preferred_browser == 'edge':
            browsers_to_try = ['edge', 'chrome']
        elif self.preferred_browser == 'auto':
            # For auto mode, try Chrome first, then others if available
            available_browsers = self._detect_available_browsers()
            if 'chrome' in available_browsers:
                browsers_to_try = ['chrome']
        else:
                browsers_to_try = available_browsers
        
        last_error = None
        initialization_attempts = []
        
        for browser in browsers_to_try:
            try:
                print(f"Attempting to initialize {browser} browser...")
                if browser == 'chrome':
                    browser_instance = self._init_chrome()
                    print(f"✅ Successfully initialized Chrome browser")
                    return browser_instance
                elif browser == 'firefox':
                    browser_instance = self._init_firefox()
                    print(f"✅ Successfully initialized Firefox browser")
                    return browser_instance
                elif browser == 'edge':
                    browser_instance = self._init_edge()
                    print(f"✅ Successfully initialized Edge browser")
                    return browser_instance
            except Exception as e:
                last_error = e
                error_msg = str(e)
                initialization_attempts.append(f"{browser}: {error_msg}")
                print(f"❌ Failed to initialize {browser}: {error_msg}")
                continue
        
        # If we get here, no browser worked - provide detailed error information
        available_browsers = self._detect_available_browsers()
        
        # Create comprehensive error message
        error_details = []
        error_details.append(f"Failed to initialize any browser after trying: {', '.join(browsers_to_try)}")
        error_details.append(f"Available browser binaries detected: {', '.join(available_browsers) if available_browsers else 'None'}")
        error_details.append("Initialization attempts:")
        for attempt in initialization_attempts:
            error_details.append(f"  - {attempt}")
        
        if not available_browsers:
            error_details.append("\n🔧 SOLUTION: Install Chrome in your container:")
            error_details.append("  - Add to Dockerfile: RUN apt-get update && apt-get install -y google-chrome-stable")
            error_details.append("  - Or use a base image with Chrome pre-installed")
        else:
            error_details.append(f"\n🔧 SOLUTION: Check WebDriver setup for {available_browsers[0]}:")
            error_details.append("  - Ensure proper permissions on driver executables")
            error_details.append("  - Check for missing shared libraries")
            error_details.append("  - Verify container has necessary dependencies")
        
        final_error_msg = "\n".join(error_details)
        raise WebDriverException(final_error_msg)
    
    def _perform_ocr_on_image(self, image_data: bytes, filename: str = "") -> str:
        """Perform OCR on an image and return the extracted text."""
        try:
            image = Image.open(io.BytesIO(image_data))
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            print(f"Failed to OCR {filename}: {e}")
            return ""
    
    def _fetch_docsend_sync(self, browser: webdriver.Chrome, url: str, 
                           email: str, password: Optional[str] = None,
                           progress_callback=None) -> Dict[str, Any]:
        """
        Fetch content from a DocSend URL with progress tracking.
        Returns structured data with OCR'd text and metadata.
        """
        try:
            if progress_callback:
                progress_callback(10, "Loading DocSend page...")
            
            browser.get(url)
            # Human-like delay - vary between 2-4 seconds
            import random
            time.sleep(random.uniform(2.5, 4.0))
            
            # Wait for page to be fully loaded
            WebDriverWait(browser, 10).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Handle email prompt first (most common)
            try:
                # Find the visible email input (not hidden feedback forms)
                email_input = None
                email_selectors = [
                    "input[name='link_auth_form[email]']",  # Specific DocSend access form
                    "input[id='link_auth_form_email']",     # Alternative ID selector
                    "input[type='email']",                  # Generic email inputs
                    "input[name='email']", 
                    "input[placeholder*='email' i]"
                ]
                
                for selector in email_selectors:
                    try:
                        potential_inputs = browser.find_elements(By.CSS_SELECTOR, selector)
                        for input_elem in potential_inputs:
                            if input_elem.is_displayed() and input_elem.is_enabled():
                                email_input = input_elem
                                print(f"Found visible email input with selector: {selector}")
                                break
                        if email_input:
                            break
                    except:
                        continue
                
                if not email_input:
                    # Fallback to wait for any clickable email input
                    email_input = WebDriverWait(browser, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='email' i]"))
                    )
                
                if progress_callback:
                    progress_callback(15, "Entering email...")
                
                # Scroll to element to ensure it's visible
                browser.execute_script("arguments[0].scrollIntoView(true);", email_input)
                time.sleep(random.uniform(0.5, 1.0))
                
                # Try to interact with the element
                try:
                    email_input.clear()
                except:
                    # If clear fails, try clicking first then clearing
                    try:
                        email_input.click()
                        time.sleep(random.uniform(0.3, 0.7))
                        email_input.clear()
                    except:
                        # If still fails, use JavaScript to clear
                        browser.execute_script("arguments[0].value = '';", email_input)
                
                # Send the email with human-like typing speed
                for char in email:
                    email_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))  # Random typing delay
                
                # Look for submit button with better detection
                submit_clicked = False
                submit_selectors = [
                    "input[value='Continue']",              # DocSend continue button (most common)
                    "input[type='submit'][value='Continue']", # Specific continue submit
                    "button:contains('Continue')",          # Continue button text
                    "input[name='commit'][value='Continue']", # DocSend commit with Continue value
                    "input[name='commit']",                 # DocSend specific submit
                    "button[type='submit']",
                    "input[type='submit']", 
                    "button:contains('Submit')",
                    "button:contains('Access')",
                    "button:contains('View')",
                    ".submit-button",
                    ".continue-button"
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_buttons = browser.find_elements(By.CSS_SELECTOR, selector)
                        for submit_button in submit_buttons:
                            if submit_button.is_enabled() and submit_button.is_displayed():
                                button_text = submit_button.text or submit_button.get_attribute('value') or 'no-text'
                                print(f"Found button: '{button_text}' with selector: {selector}")
                                print(f"Clicking submit button with selector: {selector}")
                                browser.execute_script("arguments[0].click();", submit_button)
                                submit_clicked = True
                                break
                        if submit_clicked:
                            break
                    except Exception as e:
                        print(f"Error with selector {selector}: {e}")
                        continue
                
                # If no specific selectors worked, try finding any button with "Continue" text
                if not submit_clicked:
                    try:
                        all_buttons = browser.find_elements(By.TAG_NAME, "button")
                        all_inputs = browser.find_elements(By.TAG_NAME, "input")
                        
                        for element in all_buttons + all_inputs:
                            if element.is_displayed() and element.is_enabled():
                                text = element.text or element.get_attribute('value') or ''
                                if 'continue' in text.lower():
                                    print(f"Found Continue button by text search: '{text}'")
                                    browser.execute_script("arguments[0].click();", element)
                                    submit_clicked = True
                                    break
                    except Exception as e:
                        print(f"Error in text-based button search: {e}")
                
                if not submit_clicked:
                    # Fallback: try pressing Enter
                    email_input.send_keys(Keys.RETURN)
                
                # Human-like delay after submission
                time.sleep(random.uniform(2.5, 4.0))
                
                # Check if email submission was successful
                print(f"After email submission - URL: {browser.current_url}")
                print(f"After email submission - Title: {browser.title}")
                
                # Wait for the email popup/modal to disappear (key insight!)
                print("Waiting for email popup to disappear...")
                try:
                    # Wait for the email form to disappear (indicating successful submission)
                    WebDriverWait(browser, 10).until_not(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='link_auth_form[email]']"))
                    )
                    print("✅ Email popup disappeared - submission successful!")
                except TimeoutException:
                    print("⚠️ Email popup still present - submission may have failed")
                
                # Wait a bit longer for deck content to load dynamically
                time.sleep(random.uniform(2.0, 3.0))
                
            except TimeoutException:
                # No email required, continue
                pass
            except Exception as e:
                print(f"Email input handling failed: {str(e)}")
                # Continue anyway - maybe email isn't required
                pass
            
            # Handle password prompt if present (after email)
            try:
                password_input = WebDriverWait(browser, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
                )
                if not password:
                    return {
                        'success': False,
                        'error': 'Password protected deck - no password provided',
                        'content': '',
                        'metadata': {}
                    }
                
                if progress_callback:
                    progress_callback(20, "Entering password...")
                
                # Scroll to element to ensure it's visible
                browser.execute_script("arguments[0].scrollIntoView(true);", password_input)
                time.sleep(random.uniform(0.5, 1.0))
                
                # Try to interact with the element
                try:
                    password_input.clear()
                except:
                    # If clear fails, try clicking first then clearing
                    try:
                        password_input.click()
                        time.sleep(random.uniform(0.3, 0.7))
                        password_input.clear()
                    except:
                        # If still fails, use JavaScript to clear
                        browser.execute_script("arguments[0].value = '';", password_input)
                
                # Send the password with human-like typing speed
                for char in password:
                    password_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))  # Random typing delay
                
                # Look for submit button with better detection
                submit_clicked = False
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']", 
                    "button:contains('Continue')",
                    "button:contains('Submit')",
                    "button:contains('Access')",
                    "button:contains('View')",
                    ".submit-button",
                    ".continue-button"
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_button = browser.find_element(By.CSS_SELECTOR, selector)
                        if submit_button.is_enabled() and submit_button.is_displayed():
                            browser.execute_script("arguments[0].click();", submit_button)
                            submit_clicked = True
                            break
                    except:
                        continue
                
                if not submit_clicked:
                    # Fallback: try pressing Enter
                    password_input.send_keys(Keys.RETURN)
                
                time.sleep(3)
            except TimeoutException:
                pass  # No password required
            except Exception as e:
                print(f"Password input handling failed: {str(e)}")
                # Continue anyway - maybe password isn't required
                pass
            
            if progress_callback:
                progress_callback(30, "Finding deck pages...")
            
            # Wait for page to fully load and check for deck content
            time.sleep(2)
            
            # Debug: Check current page state
            print(f"Looking for deck content - URL: {browser.current_url}")
            print(f"Looking for deck content - Title: {browser.title}")
            
            # Check if deck is available - DocSend shows one image per page
            deck_found = False
            current_page_image = None
            
            print("Searching for deck content (single page image)...")
            
            # Wait for the main deck image to load after email popup disappears
            try:
                print("  Looking for main deck page image...")
                WebDriverWait(browser, 15).until(
                    lambda driver: len(driver.find_elements(By.TAG_NAME, "img")) > 0
                )
                
                # Get all images and find the main deck page image
                all_images = browser.find_elements(By.TAG_NAME, "img")
                print(f"  Found {len(all_images)} total images")
                
                # Look for the main content image (usually the largest visible image)
                for img in all_images:
                    try:
                        src = img.get_attribute('src') or ''
                        alt = img.get_attribute('alt') or ''
                        width = img.size.get('width', 0)
                        height = img.size.get('height', 0)
                        is_displayed = img.is_displayed()
                        
                        print(f"    Image: {src[:50]}... size={width}x{height} visible={is_displayed}")
                        
                        # Check if this looks like the main deck page image
                        is_main_image = (
                            is_displayed and
                            width > 300 and height > 200  # Reasonable presentation size
                        )
                        
                        if is_main_image and not current_page_image:
                            current_page_image = img
                            print(f"    ✅ Found main deck image: {src[:60]}... size={width}x{height}")
                            deck_found = True
                    
                    except Exception as e:
                        print(f"    Error analyzing image: {e}")
                        continue
                
                if not current_page_image:
                    print(f"  ⚠️ No main deck image found, trying largest image...")
                    # Fallback: use the largest visible image
                    largest_image = None
                    largest_size = 0
                    
                    for img in all_images:
                        try:
                            if img.is_displayed():
                                width = img.size.get('width', 0)
                                height = img.size.get('height', 0)
                                size = width * height
                                if size > largest_size and width > 100 and height > 100:
                                    largest_image = img
                                    largest_size = size
                        except:
                            continue
                    
                    if largest_image:
                        current_page_image = largest_image
                        deck_found = True
                        print(f"    ✅ Using largest image as deck content")
                
            except TimeoutException:
                print(f"  ❌ No images found after waiting")
                
            # If no images found, try traditional selectors as fallback
            if not deck_found:
                print("  Trying traditional page selectors as fallback...")
                traditional_selectors = [".page", ".slide", "[data-page]", ".document-page"]
                for selector in traditional_selectors:
                    try:
                        elements = WebDriverWait(browser, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        found_elements = browser.find_elements(By.CSS_SELECTOR, selector)
                        print(f"  ✅ Found {len(found_elements)} elements with {selector}")
                        deck_found = True
                        break
                    except TimeoutException:
                        continue
            
            if not deck_found:
                # Check if we're still on an access/login page
                page_source = browser.page_source.lower()
                current_url = browser.current_url
                page_title = browser.title
                
                # Provide more specific error messages based on page content
                if 'approval' in page_source or 'pending' in page_source:
                    error_msg = 'Deck requires manual approval from owner. Contact deck owner to request access.'
                elif 'verify' in page_source or 'verification' in page_source:
                    error_msg = 'Email verification required. Check your email for verification link and try again.'
                elif 'password' in page_source and 'incorrect' in page_source:
                    error_msg = 'Incorrect password provided. Check password and try again.'
                elif 'email' in page_source and 'invalid' in page_source:
                    error_msg = 'Invalid email address. Use a valid email address.'
                elif any(keyword in page_source for keyword in ['email', 'password', 'access', 'login']):
                    error_msg = 'Deck requires additional verification or access denied. Check email/password.'
                elif 'restricted' in page_source or 'private' in page_source:
                    error_msg = 'Deck is private or restricted. Contact owner for access.'
                else:
                    error_msg = 'No deck found or access denied'
                
                return {
                    'success': False,
                    'error': error_msg,
                    'content': '',
                    'metadata': {},
                    'debug_info': {
                        'current_url': current_url,
                        'page_title': page_title,
                        'page_indicators': {
                            'has_email_fields': 'email' in page_source,
                            'has_password_fields': 'password' in page_source,
                            'has_verification': 'verify' in page_source,
                            'has_approval': 'approval' in page_source,
                            'has_restricted': 'restricted' in page_source or 'private' in page_source
                        }
                    }
                }
            
            # Process the deck using single-image-per-page approach
            if not current_page_image:
                return {
                    'success': False,
                    'error': 'No deck content image found',
                    'content': '',
                    'metadata': {}
                }
            
            print(f"✅ Found deck content! Processing pages...")
            
            # Look for navigation elements to determine total pages
            total_pages = 1  # At least one page (current)
            
            # Try to find page indicators or navigation
            try:
                # Look for page numbers or navigation elements
                page_indicators = browser.find_elements(By.CSS_SELECTOR, 
                    "[class*='page'], [id*='page'], .pagination, .nav, [aria-label*='page']")
                
                for indicator in page_indicators:
                    try:
                        text = indicator.text or indicator.get_attribute('aria-label') or ''
                        # Look for patterns like "1 of 10", "Page 1/10", etc.
                        import re
                        matches = re.findall(r'(\d+)\s*(?:of|/)\s*(\d+)', text.lower())
                        if matches:
                            current_page, total = matches[0]
                            total_pages = int(total)
                            print(f"  📊 Found page indicator: {current_page} of {total_pages}")
                            break
                    except:
                        continue
                        
            except Exception as e:
                print(f"  ⚠️ Could not determine total pages: {e}")
            
            print(f"  📋 Processing {total_pages} page(s)...")
            
            if progress_callback:
                progress_callback(40, f"Processing {total_pages} slides...")
            
            # Process each page with OCR using single-image navigation
            all_text = []
            slide_texts = []  # Keep individual slide texts for better structure
            
            for page_num in range(total_pages):
                if progress_callback:
                    progress = 40 + (page_num / total_pages) * 50  # 40-90% range
                    progress_callback(int(progress), f"OCR processing slide {page_num + 1}/{total_pages}")
                
                try:
                    print(f"  📄 Processing page {page_num + 1}/{total_pages}")
                    
                    # Get the current page image
                    page_image = current_page_image
                    
                    # For pages after the first, we need to navigate
                    if page_num > 0:
                        print(f"    🔄 Navigating to page {page_num + 1}")
                        
                        # Look for next/forward navigation elements
                        navigation_found = False
                        nav_selectors = [
                            "[aria-label*='next']",
                            "[aria-label*='forward']", 
                            ".next",
                            ".forward",
                            "button:contains('Next')",
                            "button:contains('>')",
                            "[class*='next']",
                            "[id*='next']"
                        ]
                        
                        for nav_selector in nav_selectors:
                            try:
                                nav_elements = browser.find_elements(By.CSS_SELECTOR, nav_selector)
                                for nav_elem in nav_elements:
                                    if nav_elem.is_displayed() and nav_elem.is_enabled():
                                        print(f"      🎯 Clicking navigation: {nav_selector}")
                                        nav_elem.click()
                                        navigation_found = True
                                        break
                                if navigation_found:
                                    break
                            except:
                                continue
                        
                        if not navigation_found:
                            # Try keyboard navigation
                            print(f"      ⌨️ Trying keyboard navigation (arrow keys)")
                            try:
                                from selenium.webdriver.common.keys import Keys
                                browser.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_RIGHT)
                                navigation_found = True
                            except:
                                pass
                        
                        if navigation_found:
                            # Wait for new page to load
                            time.sleep(random.uniform(1.0, 2.0))
                            
                            # Find the updated page image
                            try:
                                new_images = browser.find_elements(By.TAG_NAME, "img")
                                for img in new_images:
                                    if img.is_displayed() and img.size.get('width', 0) > 300:
                                        page_image = img
                                        break
                            except:
                                pass
                        else:
                            print(f"      ⚠️ Could not navigate to page {page_num + 1}")
                            continue
                    
                    # Take screenshot of the current page image
                    if page_image:
                        screenshot = page_image.screenshot_as_png
                        
                        text = self._perform_ocr_on_image(screenshot, f"slide_{page_num + 1}")
                        if text:
                            all_text.append(text)
                            slide_texts.append({
                                'slide_number': page_num + 1,
                                'text': text,
                                'length': len(text)
                            })
                            print(f"    ✅ Extracted {len(text)} characters from page {page_num + 1}")
                        else:
                            print(f"    ⚠️ No text extracted from page {page_num + 1}")
                    
                    time.sleep(random.uniform(0.5, 1.0))  # Human-like delay between pages
                    
                except Exception as e:
                    print(f"    ❌ Error processing slide {page_num + 1}: {e}")
                    continue
            
            if progress_callback:
                progress_callback(95, "Finalizing extraction...")
            
            combined_text = " ".join(all_text) if all_text else ""
            
            # Create metadata
            metadata = {
                'source_type': 'docsend_deck',
                'total_slides': total_pages,
                'processed_slides': len(slide_texts),
                'total_characters': len(combined_text),
                'slides_with_text': len([s for s in slide_texts if s['text']]),
                'processing_time': time.time(),  # Will be calculated by caller
                'url': url
            }
            
            if progress_callback:
                progress_callback(100, f"Completed! Extracted text from {len(slide_texts)}/{total_pages} slides")
            
            return {
                'success': True,
                'content': combined_text,
                'slide_texts': slide_texts,
                'metadata': metadata,
                'error': None
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DocSend processing exception: {error_details}")
            
            # Add debugging information
            debug_info = {
                'error_details': error_details,
                'url': url,
                'browser_title': 'Unknown',
                'page_source_snippet': 'Unknown'
            }
            
            try:
                debug_info['browser_title'] = browser.title
                page_source = browser.page_source
                debug_info['page_source_snippet'] = page_source[:500] if page_source else 'No page source'
            except:
                pass
            
            return {
                'success': False,
                'error': f"DocSend processing failed: {str(e)}",
                'content': '',
                'metadata': {},
                'debug_info': debug_info
            }
    
    async def fetch_docsend_async(self, url: str, email: str, 
                                 password: Optional[str] = None,
                                 progress_callback=None) -> Dict[str, Any]:
        """
        Asynchronous wrapper for DocSend processing.
        Returns structured data with success status, content, and metadata.
        """
        browser = None
        start_time = time.time()
        
        try:
            def sync_fetch():
                nonlocal browser
                browser = self._init_browser()
                return self._fetch_docsend_sync(browser, url, email, password, progress_callback)
            
            # Run synchronous code in thread
            result = await asyncio.to_thread(sync_fetch)
            
            # Add processing time to metadata
            if result.get('metadata'):
                result['metadata']['processing_time'] = time.time() - start_time
            
            return result
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Async DocSend processing exception: {error_details}")
            return {
                'success': False,
                'error': f"Async DocSend processing failed: {str(e)}",
                'content': '',
                'metadata': {},
                'debug_info': error_details
            }
        finally:
            if browser:
                try:
                    browser.quit()
                except:
                    pass 