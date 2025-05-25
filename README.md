# AI Research Agent

A comprehensive AI-powered research platform designed for due diligence, document analysis, and automated content extraction. Features advanced DocSend processing, multi-format document support, web scraping, Notion automation, and intelligent AI analysis.

---

## ✨ Key Features

### 🔍 **Interactive Research**
- **DocSend Integration**: Automated processing of DocSend presentations with email authentication, stealth browsing, and OCR text extraction
- **Multi-Format Document Support**: PDF, DOCX, TXT, MD, and image-based documents with OCR capabilities
- **Web Content Intelligence**: Firecrawl integration with sitemap discovery and batch URL processing
- **AI-Powered Analysis**: Generate comprehensive research reports using multiple LLM providers
- **RAG-Powered Chat**: Ask questions about your research with context-aware responses

### 🤖 **Notion Automation**
- **CRM Integration**: Monitor and automate Notion database workflows
- **Automated Research**: Run scheduled research pipelines on new entries
- **Smart Scoring**: AI-powered scoring and analysis of Notion pages
- **Automated Writing**: Generate and publish reports directly to Notion
- **Real-time Monitoring**: Watch for changes and trigger automated workflows



### 🔐 **Security & Authentication**
- **User Authentication**: Secure login/signup with bcrypt password hashing
- **Role-Based Access**: Admin and researcher roles with different permissions
- **Session Management**: Secure session handling with user-specific configurations
- **Audit Logging**: Comprehensive logging of all user actions and system events

### 🚀 **Modern Architecture**
- **Streamlit Interface**: Intuitive web-based UI for all research tasks
- **Docker Deployment**: Containerized application with Docker Compose
- **Modular Design**: Clean separation of concerns with controller-based architecture
- **Async Processing**: High-performance async operations for web scraping and AI calls

---

## 🛠️ Technology Stack

### **Core Technologies**
- **Backend & UI**: Python 3.11+, Streamlit, FastAPI
- **AI Integration**: OpenRouter API (GPT-4, Claude, Gemini, etc.)
- **Web Scraping**: Firecrawl OSS, Playwright, BeautifulSoup4
- **OCR Processing**: Tesseract, Pillow, PyMuPDF
- **Browser Automation**: Selenium WebDriver with stealth capabilities

### **Document Processing**
- **PDF**: PyMuPDF (fitz) for text and image extraction
- **DOCX**: python-docx for Word document processing
- **Images**: Pillow + Tesseract for OCR text extraction
- **Web**: BeautifulSoup4 for HTML parsing and content extraction

### **AI & Machine Learning**
- **LLM Access**: OpenRouter for multiple AI model providers
- **Embeddings**: Sentence Transformers for semantic search
- **Vector Search**: FAISS for efficient similarity search
- **RAG**: Retrieval-Augmented Generation for context-aware responses

### **Infrastructure**
- **Caching**: Redis for web content and processing results
- **Storage**: YAML-based configuration and user management
- **Logging**: Python logging with comprehensive audit trails
- **Containerization**: Docker and Docker Compose for easy deployment

---

## 📋 DocSend Processing Capabilities

### **Automated Authentication**
- **Email Form Detection**: Automatically detects and fills email authentication forms
- **Popup Handling**: Waits for authentication popups to disappear after successful submission
- **Password Support**: Handles password-protected decks when credentials are provided
- **Multi-Browser Support**: Chrome, Firefox, and Edge with automatic fallback

### **Stealth Browsing**
- **Bot Detection Avoidance**: Advanced browser configuration to bypass automation detection
- **Human-like Behavior**: Random delays, realistic typing patterns, and natural navigation
- **User Agent Spoofing**: Platform-specific user agents for better compatibility
- **JavaScript Execution**: Removes webdriver properties and adds human-like browser characteristics

### **Content Extraction**
- **Single-Page Navigation**: Handles DocSend's single-image-per-page presentation format
- **Automatic Page Detection**: Discovers total page count from navigation indicators
- **Smart Navigation**: Uses multiple navigation strategies (buttons, keyboard, selectors)
- **OCR Processing**: Extracts text from each page image with high accuracy

### **Error Handling**
- **Intelligent Error Detection**: Provides specific error messages for different failure scenarios
- **Retry Mechanisms**: Automatic retries with exponential backoff
- **Fallback Strategies**: Multiple approaches for element detection and interaction
- **Debug Information**: Comprehensive logging for troubleshooting

---

## 🗺️ Project Structure

```text
.
├── config/                     # Configuration files
│   └── users.yaml             # User credentials and settings (gitignored)
├── logs/                      # Application and audit logs (gitignored)
├── output/                    # Generated reports and outputs (gitignored)
├── src/                       # Core application source code
│   ├── controllers/           # Application controllers
│   │   ├── __init__.py
│   │   └── app_controller.py  # Main app controller with routing
│   ├── pages/                 # Streamlit page components
│   │   ├── __init__.py
│   │   ├── base_page.py       # Base page class
│   │   ├── interactive_research.py # Main research interface
│   │   └── notion_automation.py    # Notion automation features
│   ├── core/                  # Core processing modules
│   │   ├── __init__.py
│   │   ├── docsend_client.py  # DocSend processing with OCR
│   │   ├── rag_utils.py       # RAG and embedding utilities
│   │   └── scanner_utils.py   # Web scanning and discovery
│   ├── models/                # Data models and schemas
│   │   ├── __init__.py
│   │   └── chat_models.py     # Chat session models
│   ├── routers/               # API routers (FastAPI)
│   │   └── __init__.py
│   ├── __init__.py
│   ├── audit_logger.py        # Audit logging setup
│   ├── config.py             # Centralized configuration
│   ├── firecrawl_client.py   # Firecrawl OSS integration
│   ├── init_users.py         # User initialization script
│   ├── openrouter.py         # OpenRouter API client
│   ├── research.py           # Research automation
│   ├── notion_*.py           # Notion integration modules
│   └── writer.py             # Report writing utilities
├── tests/                     # Test files
│   ├── __init__.py
│   ├── test_firecrawl.py     # Firecrawl integration tests
│   ├── test_notion_connection.py # Notion API tests
│   ├── test_research.py      # Research functionality tests
│   └── test_*.py             # Additional test modules
├── web_research/              # Alternative research interface
│   ├── __init__.py
│   ├── app.py                # Standalone research app
│   ├── deep_research.py      # Deep research algorithms
│   └── ai/                   # AI processing modules
├── cache/                     # Cache directory (gitignored)
├── reports/                   # Generated reports (gitignored)
├── .env.example              # Environment variables template
├── .gitignore               # Git ignore patterns
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # Docker image definition
├── main.py                  # Main application entry point
├── requirements.txt         # Consolidated Python dependencies
└── README.md               # This file
```

---

## 🚀 Quick Start

### Prerequisites
- **Docker & Docker Compose**: [Install Docker](https://docs.docker.com/get-docker/)
- **Firecrawl OSS**: [Self-hosted instance](https://github.com/mendableai/firecrawl) (optional)
- **Redis**: For caching (can be included in Docker Compose)
- **OpenRouter API Key**: [Get API key](https://openrouter.ai/)

### 1. Clone and Setup
```bash
git clone <repository-url>
cd ai-research-agent
cp .env.example .env
```

### 2. Configure Environment
Edit `.env` with your settings:
```env
# OpenRouter Configuration (Required)
OPENROUTER_API_KEY="your_openrouter_api_key"
OPENROUTER_DEFAULT_MODEL="openai/gpt-4o"

# Firecrawl Configuration (Optional)
FIRECRAWL_API_URL="http://host.docker.internal:3002/v0/scrape"

# Redis Configuration (Optional)
REDIS_URL="redis://host.docker.internal:6379/0"

# Application Settings
STREAMLIT_SERVER_PORT="8501"
PYTHONPATH="/app"

# OCR Configuration (Auto-detected)
TESSERACT_CMD="/usr/bin/tesseract"
```

### 3. Install Dependencies
```bash
# Option 1: Using Docker (Recommended)
docker-compose build
docker-compose up -d

# Option 2: Local Installation
pip install -r requirements.txt
playwright install  # For web scraping
streamlit run main.py
```

### 4. Access Application
Open `http://localhost:8501` in your browser.

### 5. Initial Setup
- **Create Account**: Use the signup form to create your first user account
- **Configure API Keys**: Add your OpenRouter API key in the environment
- **Test Features**: Try uploading a document or processing a DocSend deck

---

## 📖 Usage Guide

### **Interactive Research Workflow**

#### 1. **Document Processing**
```bash
# Upload documents via the web interface
- PDF files (with OCR for scanned documents)
- DOCX Word documents
- TXT and Markdown files
- Multiple files for batch processing
```

#### 2. **DocSend Processing**
```bash
# Process DocSend presentations
1. Enter DocSend URL: https://docsend.com/view/...
2. Provide email address for authentication
3. Add password if deck is password-protected
4. Click "Process DocSend Deck"
5. Wait for OCR extraction to complete
```

#### 3. **Web Content Extraction**
```bash
# Scrape web content
- Enter individual URLs for targeted scraping
- Use sitemap discovery for comprehensive site analysis
- Batch process multiple URLs simultaneously
- Leverage Firecrawl for intelligent content extraction
```

#### 4. **AI Analysis**
```bash
# Generate comprehensive reports
1. Define research query or questions
2. Select AI model (GPT-4, Claude, Gemini, etc.)
3. Upload documents and/or add web content
4. Click "Generate Unified Report"
5. Review AI-generated analysis and insights
```

#### 5. **Interactive Chat**
```bash
# Ask questions about your research
- Chat interface appears after report generation
- RAG-powered responses using your research context
- Ask follow-up questions and get detailed answers
- Export chat conversations and insights
```

### **Notion Automation Features**

#### 1. **Database Monitoring**
- Connect to Notion databases
- Monitor for new entries and changes
- Trigger automated research workflows
- Score and analyze content automatically

#### 2. **Automated Research**
- Run research pipelines on new Notion entries
- Generate reports and insights automatically
- Update Notion pages with research results
- Schedule periodic research updates

#### 3. **Content Generation**
- AI-powered content creation for Notion pages
- Automated report writing and publishing
- Smart content scoring and analysis
- Integration with research workflows

---

## ⚙️ Configuration

### **Environment Variables**
```env
# Required Configuration
OPENROUTER_API_KEY=your_api_key              # OpenRouter API access
OPENROUTER_DEFAULT_MODEL=openai/gpt-4o       # Default AI model

# Optional Configuration
FIRECRAWL_API_URL=http://localhost:3002/v0/scrape  # Firecrawl endpoint
REDIS_URL=redis://localhost:6379/0                 # Redis cache
TESSERACT_CMD=/usr/bin/tesseract                   # OCR engine path
LOG_LEVEL=INFO                                     # Logging level
MAX_WORKERS=4                                      # Parallel processing
CACHE_TTL=3600                                     # Cache expiration
```

### **User Management**
- **Default Users**: Admin and researcher accounts created on first run
- **Custom Users**: Create additional users via the signup interface
- **Role Permissions**: Different access levels for admin and researcher roles
- **Session Persistence**: User preferences and settings saved across sessions

### **AI Model Configuration**
```python
# Available models through OpenRouter
SUPPORTED_MODELS = {
    "openai/gpt-4o": "GPT-4 Omni (Latest)",
    "anthropic/claude-3-sonnet": "Claude 3 Sonnet",
    "google/gemini-pro": "Gemini Pro",
    "meta-llama/llama-2-70b-chat": "Llama 2 70B Chat",
    "mistralai/mixtral-8x7b-instruct": "Mixtral 8x7B Instruct"
}
```

### **System Dependencies**
```bash
# Browsers (at least one required)
- Chrome/Chromium (recommended for DocSend)
- Firefox
- Microsoft Edge

# OCR Engine
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki

# Playwright Browsers (for web scraping)
playwright install
```

---

## 🔧 Advanced Features

### **DocSend Troubleshooting**
- **Debug Mode**: Enable verbose logging for DocSend processing
- **Browser Selection**: Choose between Chrome, Firefox, or Edge
- **Stealth Configuration**: Advanced anti-detection measures
- **Manual Intervention**: Pause processing for manual verification

### **OCR Optimization**
- **Language Support**: Configure Tesseract for multiple languages
- **Image Preprocessing**: Enhance image quality before OCR
- **Confidence Scoring**: Filter OCR results by confidence levels
- **Custom Training**: Use custom Tesseract models for specialized content

### **Performance Tuning**
- **Parallel Processing**: Configure worker threads for batch operations
- **Memory Management**: Optimize memory usage for large documents
- **Cache Strategy**: Fine-tune Redis caching for optimal performance
- **Rate Limiting**: Configure API rate limits and retry strategies

### **Notion Integration**
- **Database Connections**: Connect to multiple Notion databases
- **Automated Workflows**: Set up triggers and automated actions
- **Content Synchronization**: Keep research data synchronized with Notion
- **Custom Properties**: Map research data to custom Notion properties

---

## 🐛 Troubleshooting

### **Common Issues**

#### DocSend Processing Fails
```bash
# Check browser installation
python -c "from selenium import webdriver; print('Selenium OK')"

# Test OCR functionality
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"

# Verify network connectivity
curl -I https://docsend.com
```

#### Firecrawl Connection Issues
```bash
# Test Firecrawl endpoint
curl -X POST http://localhost:3002/v0/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

#### Redis Connection Problems
```bash
# Test Redis connectivity
redis-cli ping

# Check Redis configuration
redis-cli config get "*"
```

#### OpenRouter API Issues
```bash
# Test API connection
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-3.5-turbo", "messages": [{"role": "user", "content": "test"}]}'
```

### **Debug Mode**
Enable comprehensive debugging:
```env
LOG_LEVEL=DEBUG
SELENIUM_DEBUG=true
STREAMLIT_LOGGER_LEVEL=debug
```

### **Browser Issues**
- **Headless Mode**: Disable for visual debugging
- **User Agent**: Update user agent strings for compatibility
- **Permissions**: Ensure proper file system permissions
- **Dependencies**: Verify all browser drivers are installed

---

## 🔒 Security Considerations

### **Data Privacy**
- **Local Processing**: Documents processed locally by default
- **API Security**: Secure API key management with environment variables
- **User Data**: Encrypted password storage using bcrypt
- **Session Security**: Secure session management with timeout handling

### **Network Security**
- **HTTPS**: Use HTTPS for production deployments
- **Firewall**: Configure appropriate firewall rules
- **VPN**: Consider VPN for sensitive research tasks
- **Audit Trail**: Comprehensive logging of all user activities

### **Access Control**
- **Role-Based Permissions**: Different access levels for users
- **Session Management**: Automatic session timeout and cleanup
- **API Rate Limiting**: Prevent abuse of external APIs
- **Input Validation**: Sanitize all user inputs and uploads

---

## 🤝 Contributing

### **Development Setup**
```bash
# Clone repository
git clone <repository-url>
cd ai-research-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
playwright install

# Install system dependencies
# macOS: brew install tesseract
# Ubuntu: sudo apt-get install tesseract-ocr

# Run tests
python -m pytest tests/

# Start development server
streamlit run main.py
```

### **Code Standards**
- **PEP 8**: Follow Python style guidelines
- **Type Hints**: Use type annotations for better code clarity
- **Documentation**: Document all functions and classes
- **Testing**: Write tests for new features
- **Async/Await**: Use async patterns for I/O operations

### **Architecture Guidelines**
- **MVC Pattern**: Separate controllers, models, and views
- **Dependency Injection**: Use dependency injection for services
- **Error Handling**: Implement comprehensive error handling
- **Logging**: Add appropriate logging for debugging and monitoring

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🆘 Support

### **Documentation**
- **API Reference**: Detailed API documentation in `/docs`
- **Examples**: Sample configurations and use cases in `/examples`
- **FAQ**: Frequently asked questions and solutions

### **Community**
- **Issues**: Report bugs and request features on GitHub
- **Discussions**: Join community discussions for help and tips
- **Contributing**: See CONTRIBUTING.md for development guidelines

### **Professional Support**
For enterprise deployments and custom integrations, contact the development team.

---

## 🚀 Roadmap

### **Upcoming Features**
- **Multi-language OCR**: Enhanced language support for global documents
- **API Endpoints**: RESTful API for programmatic access
- **Cloud Deployment**: One-click cloud deployment options
- **Advanced Analytics**: Document similarity and trend analysis
- **Integration Plugins**: Connectors for popular research tools

### **Performance Improvements**
- **GPU Acceleration**: CUDA support for faster OCR processing
- **Distributed Processing**: Multi-node processing capabilities
- **Advanced Caching**: Intelligent content caching strategies
- **Real-time Processing**: Live document processing and analysis

### **AI Enhancements**
- **Custom Models**: Support for fine-tuned domain-specific models
- **Multi-modal Processing**: Image and video content analysis
- **Advanced RAG**: Improved retrieval and generation capabilities
- **Automated Workflows**: AI-driven research workflow automation

---


*Version: 2.0.0 - Major release with DocSend integration and consolidated architecture*


