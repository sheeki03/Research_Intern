"""
DocSend Client for AI Research Agent.
Handles DocSend deck processing with OCR text extraction.
"""

import asyncio
import io
import os
import time
from typing import Dict, Any, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from PIL import Image
import pytesseract

class DocSendClient:
    """Client for processing DocSend presentations with OCR."""
    
    def __init__(self, tesseract_cmd: str = None):
        """Initialize DocSend client with optional Tesseract path."""
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # Suppress logs
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        os.environ['PYTHONWARNINGS'] = 'ignore'
    
    def _init_browser(self) -> webdriver.Chrome:
        """Initialize and return a configured Chrome browser instance."""
        chrome_options = Options()
        user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
        
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument(f'user-agent={user_agent}')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument("--window-size=1200,900")
        
        return webdriver.Chrome(options=chrome_options)
    
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
            time.sleep(2)
            
            # Handle password prompt if present
            try:
                password_input = WebDriverWait(browser, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
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
                
                password_input.send_keys(password)
                password_input.send_keys(Keys.RETURN)
                time.sleep(2)
            except TimeoutException:
                pass  # No password required
            
            if progress_callback:
                progress_callback(30, "Finding deck pages...")
            
            # Check if deck is available
            try:
                WebDriverWait(browser, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "page"))
                )
            except TimeoutException:
                return {
                    'success': False,
                    'error': 'No deck found or access denied',
                    'content': '',
                    'metadata': {}
                }
            
            # Get all pages
            pages = browser.find_elements(By.CLASS_NAME, "page")
            total_pages = len(pages)
            
            if total_pages == 0:
                return {
                    'success': False,
                    'error': 'No pages found in deck',
                    'content': '',
                    'metadata': {}
                }
            
            if progress_callback:
                progress_callback(40, f"Processing {total_pages} slides...")
            
            # Process each page with OCR
            all_text = []
            slide_texts = []  # Keep individual slide texts for better structure
            
            for page_num in range(total_pages):
                if progress_callback:
                    progress = 40 + (page_num / total_pages) * 50  # 40-90% range
                    progress_callback(int(progress), f"OCR processing slide {page_num + 1}/{total_pages}")
                
                try:
                    page = browser.find_elements(By.CLASS_NAME, "page")[page_num]
                    screenshot = page.screenshot_as_png
                    
                    text = self._perform_ocr_on_image(screenshot, f"slide_{page_num + 1}")
                    if text:
                        all_text.append(text)
                        slide_texts.append({
                            'slide_number': page_num + 1,
                            'text': text,
                            'length': len(text)
                        })
                    
                    time.sleep(0.5)  # Small delay between pages
                    
                except Exception as e:
                    print(f"Error processing slide {page_num + 1}: {e}")
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
            return {
                'success': False,
                'error': f"DocSend processing failed: {str(e)}",
                'content': '',
                'metadata': {}
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
            return {
                'success': False,
                'error': f"Async DocSend processing failed: {str(e)}",
                'content': '',
                'metadata': {}
            }
        finally:
            if browser:
                try:
                    browser.quit()
                except:
                    pass 