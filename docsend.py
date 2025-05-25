from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import utils
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
from PIL import Image
import pytesseract
import re
from selenium.common.exceptions import TimeoutException
from concurrent.futures import ThreadPoolExecutor
import io
import threading
from queue import Queue
import numpy as np
import asyncio
import subprocess

# -----------------------------
# Import configuration secrets
from config import TESSERACT_CMD, DOCSEND_EMAIL, DOCSEND_PASSWORD
# -----------------------------

# Replace the hardcoded Tesseract path with the imported one
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Suppress TensorFlow and Selenium logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging
os.environ['PYTHONWARNINGS'] = 'ignore'    # Suppress Python warnings

def init_browser():
    """Initialize and return a configured Chrome browser instance."""
    chrome_options = Options()
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
    WINDOW_SIZE = "1200,900"
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(f'user-agent={user_agent}')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument('--log-level=3')  # Fatal only
    chrome_options.add_argument("--window-size=%s" % WINDOW_SIZE)
    
    browser = webdriver.Chrome(options=chrome_options)
    return browser

def perform_ocr_on_image(image_data, filename=""):
    """Perform OCR on an image and return the extracted text."""
    try:
        # Convert the image data to a PIL Image
        image = Image.open(io.BytesIO(image_data))
        
        # Perform OCR
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        print(f"Failed to OCR {filename}: {e}")
        return ""

def fetch_docsend(browser, url, email, password=None):
    """
    Fetch content from a DocSend URL. Returns a dictionary with the OCR'd text.
    Ensures all return values are JSON-serializable.
    """
    print(f"[DocSend] Scraping deck at {url}")
    try:
        browser.get(url)
        time.sleep(2)  # Short wait for initial load

        # Check for password prompt
        try:
            password_input = WebDriverWait(browser, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
            )
            print("[DocSend] Password input found")
            if not password:
                print("[DocSend] Password required but none provided.")
                return "Password protected deck - no password provided"
            password_input.send_keys(password)
            password_input.send_keys(Keys.RETURN)
            time.sleep(2)
        except TimeoutException:
            print("[DocSend] No password prompt found")

        # Check if we can find the deck
        try:
            WebDriverWait(browser, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "page"))
            )
        except TimeoutException:
            print("[DocSend] No deck found, returning early.")
            return "No deck found"

        # Get total pages
        pages = browser.find_elements(By.CLASS_NAME, "page")
        total_pages = len(pages)
        if total_pages == 0:
            return "No pages found in deck"

        # Process each page
        all_text = []
        for page_num in range(total_pages):
            print(f"[DocSend] Scraped page {page_num + 1}/{total_pages}")
            
            # Take screenshot of current page
            page = browser.find_elements(By.CLASS_NAME, "page")[page_num]
            screenshot = page.screenshot_as_png
            
            # Perform OCR
            text = perform_ocr_on_image(screenshot, f"page_{page_num + 1}")
            if text:
                all_text.append(text)
            
            # Small delay between pages
            time.sleep(0.5)

        # Return combined text
        return " ".join(all_text) if all_text else "No text extracted from deck"

    except Exception as e:
        print(f"[DocSend Error] Failed to scrape deck: {e}")
        return f"Error scraping deck: {str(e)}"

async def fetch_docsend_async(url, email, password=None):
    """
    Asynchronous wrapper for fetch_docsend.
    Ensures the return value is JSON-serializable.
    """
    try:
        browser = None
        result = None
        
        def sync_fetch():
            nonlocal browser, result
            browser = init_browser()
            result = fetch_docsend(browser, url, email, password)
            
        # Run the synchronous code in a thread
        await asyncio.to_thread(sync_fetch)
        
        # Clean up
        if browser:
            browser.quit()
            
        # Ensure we return a JSON-serializable value
        if isinstance(result, str):
            return result
        elif result is None:
            return "Failed to scrape deck"
        else:
            return str(result)
            
    except Exception as e:
        print(f"[DocSend Async Error] {e}")
        return f"Error in async deck scraping: {str(e)}"

if __name__ == '__main__':
    # Test the async function
    async def test():
        result = await fetch_docsend_async(
            url="https://docsend.com/view/s/example",
            email=DOCSEND_EMAIL
        )
        print("Result:", result)

    asyncio.run(test())
    