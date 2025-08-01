# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install system dependencies for multi-browser support
RUN apt-get update && apt-get install -y \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    # Selenium dependencies
    wget \
    gnupg2 \
    software-properties-common \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    # Firefox for Selenium fallback
    firefox-esr \
    && rm -rf /var/lib/apt/lists/*

# Install Chromium and ChromeDriver (better ARM64 support)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for browser binaries
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for our enhanced version
RUN pip install --no-cache-dir \
    streamlit \
    bcrypt \
    pyyaml \
    python-docx \
    fastapi \
    uvicorn

# Install Playwright browsers (all supported browsers)
RUN playwright install chromium firefox webkit
RUN playwright install-deps

# Copy the rest of the application
COPY . .

# Ensure config directory and files are present
RUN ls -la /app/config/ || echo "Config directory not found"

# Create necessary directories
RUN mkdir -p logs reports

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port for Streamlit
EXPOSE 8501

# Command to run the application
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"] 