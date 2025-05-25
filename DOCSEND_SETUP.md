# DocSend Integration Setup Guide

## Overview

The DocSend integration allows you to extract text content from DocSend presentation decks using OCR (Optical Character Recognition). This is useful because DocSend decks typically don't allow text copying.

## Features

- **Automatic OCR Processing**: Extracts text from all slides automatically
- **Progress Tracking**: Real-time updates during processing
- **Password Support**: Handles password-protected decks
- **Caching**: Avoids reprocessing the same deck
- **Research Integration**: Includes OCR'd content in AI research reports
- **Chat Integration**: Makes DocSend content available for chat questions

## Prerequisites

### 1. Python Dependencies

Install the required Python packages:

```bash
pip install -r requirements_docsend.txt
```

This installs:
- `selenium` - Browser automation
- `pytesseract` - OCR text extraction
- `Pillow` - Image processing

### 2. System Dependencies

#### Chrome/Chromium Browser

DocSend integration requires Chrome or Chromium browser for automation.

**macOS:**
```bash
# Chrome is usually installed via download from Google
# Or install Chromium via Homebrew:
brew install --cask chromium
```

**Linux:**
```bash
# Ubuntu/Debian:
sudo apt-get install chromium-browser

# CentOS/RHEL:
sudo yum install chromium
```

#### Tesseract OCR Engine

**macOS:**
```bash
brew install tesseract
```

**Linux:**
```bash
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr

# CentOS/RHEL:
sudo yum install tesseract
```

**Windows:**
1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install and note the installation path
3. Set environment variable: `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`

### 3. Environment Variables (Optional)

If Tesseract is not in your PATH, set the location:

```bash
export TESSERACT_CMD=/usr/local/bin/tesseract  # macOS with Homebrew
# or
export TESSERACT_CMD=/usr/bin/tesseract        # Linux
```

## Usage

### 1. In the Streamlit App

1. Go to **Notion Automation** page
2. Navigate to **Step 3: Add Extra Sources**
3. Click on the **📊 DocSend Decks** tab
4. Enter:
   - **DocSend URL**: The full DocSend link (e.g., `https://docsend.com/view/abc123`)
   - **Email**: Required for DocSend access
   - **Password**: Optional, only if the deck is password-protected
5. Run **Enhanced Research** - DocSend processing will happen automatically

### 2. What Happens During Processing

1. **Browser Launch**: Headless Chrome opens and navigates to DocSend
2. **Authentication**: Enters email and password if required
3. **Slide Detection**: Finds all slides in the presentation
4. **OCR Processing**: Takes screenshots of each slide and extracts text
5. **Content Assembly**: Combines all slide text into a single document
6. **Caching**: Stores results to avoid reprocessing

### 3. Progress Tracking

You'll see real-time updates like:
- "Loading DocSend page..."
- "Entering password..."
- "OCR processing slide 3/15"
- "Completed! Extracted text from 12/15 slides"

## Troubleshooting

### Common Issues

**1. "No module named 'selenium'"**
```bash
pip install selenium
```

**2. "Tesseract not found"**
- Install Tesseract OCR engine (see prerequisites)
- Set `TESSERACT_CMD` environment variable if needed

**3. "Chrome not found"**
- Install Chrome or Chromium browser
- Ensure it's in your PATH

**4. "Password protected deck - no password provided"**
- Enter the deck password in the Password field
- Some decks require specific email domains for access

**5. "No deck found or access denied"**
- Check if the DocSend URL is correct and accessible
- Verify you have permission to view the deck
- Some decks may have IP restrictions

### OCR Quality Tips

- **Better Results**: Decks with clear, high-contrast text work best
- **Font Size**: Larger fonts are recognized more accurately
- **Language**: Tesseract works best with English text
- **Images**: Pure image slides may not extract meaningful text

### Performance Notes

- **Processing Time**: Expect 1-3 seconds per slide
- **Memory Usage**: Large decks (50+ slides) may use significant memory
- **Network**: Requires stable internet connection for DocSend access

## Security Considerations

- **Credentials**: Email and password are only used for DocSend access
- **Storage**: Passwords are not permanently stored
- **Privacy**: OCR processing happens locally on your machine
- **Caching**: Extracted content is cached in session state only

## Limitations

- **OCR Accuracy**: Text recognition isn't 100% perfect
- **Images**: Cannot extract text from images within slides
- **Formatting**: Original formatting and layout are not preserved
- **Charts/Graphs**: Data in visual charts may not be extracted
- **Rate Limits**: DocSend may have access rate limitations

## Integration Details

### Research Pipeline

DocSend content is automatically included in:
- **Enhanced Research Reports**: OCR'd text becomes part of the AI analysis
- **Chat Interface**: You can ask questions about the DocSend content
- **Source Attribution**: Reports show which slides were processed

### File Structure

```
src/core/docsend_client.py     # Main DocSend processing client
requirements_docsend.txt       # Python dependencies
DOCSEND_SETUP.md              # This setup guide
```

### Session State Variables

- `notion_docsend_content`: Extracted text content
- `notion_docsend_metadata`: Processing metadata (slide counts, timing)
- `notion_docsend_url`: Current DocSend URL
- `notion_docsend_email`: User email for access

## Support

If you encounter issues:

1. Check the **Processing Details** expander for metadata
2. Verify all prerequisites are installed
3. Test with a simple, public DocSend deck first
4. Check browser console for Selenium errors
5. Ensure Tesseract is working: `tesseract --version`

## Example Usage

```python
# Direct usage (for development/testing)
from src.core.docsend_client import DocSendClient

client = DocSendClient()
result = await client.fetch_docsend_async(
    url="https://docsend.com/view/example",
    email="user@example.com",
    password="optional_password"
)

if result['success']:
    print(f"Extracted {len(result['content'])} characters")
    print(f"Processed {result['metadata']['processed_slides']} slides")
else:
    print(f"Error: {result['error']}") 