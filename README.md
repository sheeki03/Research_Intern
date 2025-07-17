# AI Research Agent 🤖📊

> **Advanced Multi-Modal Research Platform with AI-Powered Analysis, Notion CRM Integration, and Crypto Intelligence**

A comprehensive, production-ready research automation platform that combines document processing, web scraping, AI analysis, and real-time monitoring to deliver intelligent research workflows.

## 🌟 Key Features

### 🔬 **Interactive Research Suite**
- **Multi-Format Document Processing**: PDF, DOCX, TXT, Markdown with OCR support
- **DocSend Integration**: Automated presentation analysis with stealth browsing
- **Advanced Web Scraping**: Firecrawl-powered content extraction with sitemap discovery
- **Deep Research Mode**: LangChain's Open Deep Research (ODR) framework integration
- **RAG-Powered Chat**: Context-aware Q&A about research content using FAISS vector search

### 🔗 **Notion CRM Automation**
- **Real-Time Database Monitoring**: Automated polling of Notion databases
- **Intelligent Workflow Triggers**: Research pipeline activation on new entries
- **AI-Powered Project Scoring**: Automated due diligence and evaluation
- **Direct Publishing**: Research reports published directly to Notion pages

### 💰 **Crypto Intelligence Hub**
- **Live Market Data**: Real-time cryptocurrency information via CoinGecko MCP
- **Interactive Analysis**: AI-powered crypto insights and technical analysis
- **Dynamic Visualizations**: Plotly and Altair-based charts and metrics
- **Portfolio Intelligence**: Multi-coin comparisons and trend analysis

### 🧠 **Advanced AI Integration**
- **Multi-Model Support**: GPT-4, Claude Sonnet 4, Gemini 2.5 Pro, Qwen, DeepSeek R1
- **Nano-GPT Integration**: DMind-1 and specialized models
- **OpenRouter API**: Unified access to 50+ AI models
- **Custom Research Prompts**: Specialized prompts for due diligence and analysis

## 🏗️ Architecture

### **Core Components**
```
├── main.py                     # Streamlit application entry point
├── src/
│   ├── controllers/            # Application orchestration
│   │   └── app_controller.py   # Main app controller with auth & routing
│   ├── pages/                  # Modular page implementations
│   │   ├── interactive_research.py    # Document processing & AI analysis
│   │   ├── notion_automation.py       # Notion CRM integration
│   │   ├── crypto_chatbot.py          # Crypto intelligence interface
│   │   └── voice_cloner_page.py       # Voice synthesis (experimental)
│   ├── services/               # External integrations
│   │   ├── odr_service.py             # Open Deep Research integration
│   │   ├── user_history_service.py    # Session management
│   │   └── crypto_analysis/           # Crypto data services
│   ├── core/                   # Core business logic
│   │   ├── research_engine.py         # Research automation
│   │   ├── rag_utils.py              # Vector search & embeddings
│   │   ├── scanner_utils.py          # Web discovery & parsing
│   │   └── docsend_client.py         # DocSend processing
│   └── models/                 # Data models & schemas
├── config/                     # Configuration files
│   ├── users.yaml             # User management
│   └── mcp_config.json        # MCP integrations
└── tests/                     # Comprehensive test suite
```

### **Technology Stack**
- **Backend**: Python 3.11+, Streamlit, FastAPI
- **AI/ML**: OpenAI, LangChain, FAISS, sentence-transformers
- **Browser Automation**: Selenium, Playwright
- **Document Processing**: PyMuPDF, python-docx, Tesseract OCR
- **Data**: pandas, numpy, Redis (optional)
- **Visualization**: Plotly, Altair, Bokeh

## 🚀 Quick Start

### **1. Installation**

#### **Option A: Docker (Recommended)**
```bash
git clone <repository-url>
cd ai-research-agent
cp .env.example .env
# Configure your API keys in .env
docker-compose up -d
```

#### **Option B: Local Installation**
```bash
# Clone repository
git clone <repository-url>
cd ai-research-agent

# Install Python dependencies
pip install -r requirements.txt

# Install browser dependencies
playwright install

# Install system dependencies (macOS)
brew install tesseract

# Install system dependencies (Ubuntu)
sudo apt-get install tesseract-ocr

# Install system dependencies (Windows)
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
```

### **2. Configuration**

#### **Environment Variables (.env)**
```env
# Required: AI Model Access
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional: Additional AI Providers
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
NANOGPT_API_KEY=your_nanogpt_key_here

# Optional: Notion Integration
NOTION_TOKEN=your_notion_integration_token

# Optional: Web Scraping
FIRECRAWL_API_URL=http://localhost:3002
FIRECRAWL_API_KEY=your_firecrawl_key

# Optional: Deep Research (ODR)
TAVILY_API_KEY=your_tavily_search_key

# Optional: Caching & Performance
REDIS_URL=redis://localhost:6379

# System Configuration
TESSERACT_CMD=/usr/bin/tesseract  # Adjust for your system
```

#### **User Management (config/users.yaml)**
```yaml
users:
  admin:
    username: admin
    password_hash: $2b$12$... # Use generate_password.py script
    role: admin
  researcher:
    username: researcher  
    password_hash: $2b$12$...
    role: researcher
```

### **3. Run Application**
```bash
# Local development
streamlit run main.py

# Production
streamlit run main.py --server.port 8501 --server.address 0.0.0.0
```

Visit `http://localhost:8501` and login with your configured credentials.

## 📖 Usage Guide

### **Interactive Research Workflow**

1. **🔐 Authentication**: Login with username/password
2. **📋 Research Query**: Define your research question or topic
3. **📄 Document Upload**: Upload PDF, DOCX, or text files (optional)
4. **🌐 Web Content**: Add specific URLs or enable sitemap crawling (optional)
5. **📊 DocSend Processing**: Process presentation decks with email authentication (optional)
6. **🔬 Research Mode Selection**:
   - **Classic Mode**: Traditional AI analysis of provided sources
   - **Deep Research (ODR)**: Advanced multi-agent research with web search
7. **⚙️ Configuration**: Adjust research parameters (breadth, depth, tool calls)
8. **🤖 AI Analysis**: Generate comprehensive research reports
9. **💬 Interactive Chat**: Ask questions about the research using RAG

### **Notion Automation Workflow**

1. **🔗 Notion Setup**: Configure Notion integration token
2. **📊 Database Selection**: Choose Notion database to monitor
3. **⚡ Enable Monitoring**: Start real-time database polling
4. **🎯 Configure Triggers**: Set up automated research workflows
5. **📈 AI Scoring**: Enable intelligent project evaluation
6. **📝 Report Publishing**: Automatic research report generation to Notion

### **Crypto Intelligence Workflow**

1. **🔌 MCP Connection**: Connect to CoinGecko data source
2. **💰 Coin Selection**: Choose cryptocurrencies to analyze
3. **📊 Technical Analysis**: Generate interactive charts and metrics
4. **🧠 AI Insights**: Get AI-powered market analysis and predictions
5. **📈 Portfolio Tracking**: Monitor multiple coins and trends

## 🔧 Advanced Configuration

### **Deep Research (ODR) Setup**

Deep Research uses LangChain's Open Deep Research framework for advanced multi-agent research:

```bash
# Install ODR dependencies (included in requirements.txt)
pip install langgraph langchain-community langchain-openai langchain-anthropic

# Get Tavily API key for web search
# Visit: https://tavily.com/
export TAVILY_API_KEY=your_tavily_key_here
```

**ODR Parameters for Detailed Reports:**
- **Breadth (6-15)**: Number of concurrent research units
- **Depth (4-8)**: Research iteration depth  
- **Max Tool Calls (8-15)**: Web searches per iteration

**Ultra-Comprehensive Mode**: Breadth=10, Depth=6, Tools=12 (720 total operations)

### **Model Configuration**

The platform supports multiple AI providers and models:

```python
# Available Models
AI_MODEL_OPTIONS = {
    # Nano-GPT Models  
    "dmind/dmind-1": "DMind-1",
    "dmind/dmind-1-mini": "DMind-1 Mini",
    
    # OpenRouter Models
    "qwen/qwen3-30b-a3b:free": "Qwen3 30B", 
    "qwen/qwen3-235b-a22b:free": "Qwen3 235B",
    "google/gemini-2.5-pro-preview": "Gemini 2.5 Pro",
    "openai/o3": "OpenAI o3",
    "openai/gpt-4.1": "GPT-4.1",
    "anthropic/claude-sonnet-4": "Claude Sonnet 4",
    "tngtech/deepseek-r1t-chimera:free": "DeepSeek R1T Chimera"
}
```

### **Performance Optimization**

#### **Redis Caching (Optional)**
```bash
# Install Redis
docker run -d -p 6379:6379 redis:alpine

# Configure in .env
REDIS_URL=redis://localhost:6379
```

#### **Browser Configuration**
```python
# Chrome/Chromium (Recommended for DocSend)
CHROME_BINARY=/usr/bin/google-chrome

# Firefox Alternative
FIREFOX_BINARY=/usr/bin/firefox
```

## 🔐 Security & Authentication

### **User Management**

The platform uses role-based access control:

- **Admin**: Full system access, user management
- **Researcher**: Research features, limited configuration

**Password Generation:**
```bash
python -c "
import bcrypt
password = 'your_password_here'
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
print(hashed.decode('utf-8'))
"
```

### **Security Features**

- **🔐 bcrypt Password Hashing**: Secure password storage
- **🛡️ Session Management**: Secure session tokens with expiration
- **📝 Audit Logging**: Comprehensive action tracking
- **🚧 Rate Limiting**: API abuse prevention
- **🔒 Input Validation**: Sanitized user inputs
- **🔑 API Key Management**: Environment variable security

## 🧪 Testing

### **Run Test Suite**
```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_research.py          # Research workflows
pytest tests/test_notion_connection.py # Notion integration
pytest tests/test_firecrawl.py        # Web scraping
pytest tests/test_odr_service.py      # Deep Research
pytest tests/test_browser_fix.py      # DocSend processing

# Run with coverage
pytest --cov=src tests/
```

### **Test Configuration**

Tests require API credentials for integration testing:
```env
# Add to .env for testing
NOTION_TOKEN=your_test_notion_token
FIRECRAWL_API_KEY=your_test_firecrawl_key
OPENROUTER_API_KEY=your_test_openrouter_key
```

## 🚀 Deployment

### **Docker Deployment**

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8501:8501"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - NOTION_TOKEN=${NOTION_TOKEN}
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./logs:/app/logs
      - ./reports:/app/reports
    depends_on:
      - redis
      
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

### **AWS EC2 Deployment**

```bash
# Launch EC2 instance (Ubuntu 20.04+)
# Install Docker and docker-compose
sudo apt update
sudo apt install docker.io docker-compose

# Clone and deploy
git clone <repository-url>
cd ai-research-agent
cp .env.example .env
# Configure .env with your API keys
sudo docker-compose up -d

# Set up monitoring (optional)
bash scripts/setup_monitoring.sh
```

### **Production Configuration**

```bash
# Environment setup
export STREAMLIT_SERVER_PORT=80
export STREAMLIT_SERVER_ADDRESS=0.0.0.0
export STREAMLIT_SERVER_ENABLE_CORS=false
export STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false

# Run with SSL (recommended)
streamlit run main.py \
  --server.port 443 \
  --server.sslCertFile /path/to/cert.pem \
  --server.sslKeyFile /path/to/key.pem
```

## 📊 API Integration Details

### **OpenRouter Integration**
- **50+ AI Models**: GPT, Claude, Gemini, Qwen, Llama, and more
- **Unified API**: Single interface for multiple providers
- **Rate Limiting**: Configurable requests per hour
- **Fallback Strategy**: Automatic model switching on failures

### **Notion Integration** 
- **Database Monitoring**: Real-time change detection
- **Automated Workflows**: Research pipeline triggers
- **Content Publishing**: Direct page creation and updates
- **Property Mapping**: Custom field synchronization

### **Firecrawl Integration**
- **Intelligent Scraping**: AI-powered content extraction
- **Sitemap Discovery**: Automated URL discovery
- **Batch Processing**: Multiple URL handling
- **Rate Limiting**: Respectful crawling practices

### **MCP (Model Context Protocol)**
- **CoinGecko Integration**: Live cryptocurrency data
- **Extensible Framework**: Plugin architecture for new providers
- **Type Safety**: Structured data models
- **Real-time Updates**: Live market data streams

## 🤝 Contributing

### **Development Setup**
```bash
# Fork and clone repository
git clone https://github.com/yourusername/ai-research-agent.git
cd ai-research-agent

# Create development environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run development server
streamlit run main.py
```

### **Code Style**
- **Type Hints**: Required for all functions
- **Docstrings**: Google style documentation
- **Testing**: pytest with >80% coverage
- **Linting**: flake8, black, isort
- **Security**: bandit security scanning

### **Contribution Guidelines**
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support & Documentation

### **Getting Help**
- **Issues**: [GitHub Issues](https://github.com/yourusername/ai-research-agent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/ai-research-agent/discussions)
- **Documentation**: [Wiki](https://github.com/yourusername/ai-research-agent/wiki)

### **Common Issues & Solutions**

#### **DocSend Processing Issues**
```bash
# Install Chrome/Chromium
# Ubuntu: sudo apt install google-chrome-stable
# macOS: brew install --cask google-chrome
# Windows: Download from google.com/chrome

# Verify Tesseract installation
tesseract --version
```

#### **Notion Connection Issues**
```bash
# Verify integration token
curl -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Notion-Version: 2022-06-28" \
     https://api.notion.com/v1/users/me
```

#### **Memory Issues with Large Documents**
```python
# Increase memory limits in config
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB
CHUNK_SIZE = 1000  # Reduce for memory constraints
```

## 🔄 Version History

### **Current: v2.1.0**
- ✅ Deep Research (ODR) integration
- ✅ Enhanced crypto intelligence
- ✅ Improved UI/UX
- ✅ Advanced authentication
- ✅ Comprehensive testing

### **Previous Versions**
- **v2.0.0**: Notion automation, crypto chatbot
- **v1.5.0**: DocSend integration, RAG chat
- **v1.0.0**: Basic research and document processing

## 🙏 Acknowledgments

- **LangChain**: Open Deep Research framework
- **OpenRouter**: Multi-model AI access
- **Streamlit**: Web application framework
- **Notion**: CRM integration platform
- **Firecrawl**: Web scraping service
- **CoinGecko**: Cryptocurrency data API

---

**Built with ❤️ for researchers, analysts, and knowledge workers worldwide.**

*For detailed API documentation, advanced configuration, and deployment guides, visit our [comprehensive documentation wiki](https://github.com/yourusername/ai-research-agent/wiki).*