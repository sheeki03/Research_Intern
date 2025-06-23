import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory (Research_Intern_latest root) to Python path
# This allows us to use the root .env file and configuration
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Load environment variables from the root .env file
env_path = ROOT_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# AI_Intern-main specific paths (relative to AI_Intern-main directory)
AI_INTERN_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = AI_INTERN_DIR / "logs"
REPORTS_DIR = AI_INTERN_DIR / "reports"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Required environment variables for DDQ scorer
def check_required_env() -> None:
    """Ensure that all required environment variables are present."""
    required = [
        "NOTION_TOKEN",
        "NOTION_DB_ID", 
        "OPENAI_API_KEY",
    ]
    
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"Missing environment variables from root .env: {missing_str}")

# Environment variable mappings (using root .env)
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Optional environment variables
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
DEFAULT_SCRAPER = os.getenv("DEFAULT_SCRAPER", "firecrawl")
DEEP_RESEARCH_PROMPT = os.getenv("DEEP_RESEARCH_PROMPT", "You are a world-class research analyst...")
PROJECT_SCORER_PROMPT = os.getenv("PROJECT_SCORER_PROMPT")

# Research configuration
RESEARCH_CONCURRENCY = int(os.getenv("RESEARCH_CONCURRENCY", "3"))

# System prompt for research (compatible with main web_research module)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", """YOU ARE A WORLD-CLASS DUE-DILIGENCE RESEARCH ANALYST WITH UNMATCHED EXPERTISE IN FINANCE, BLOCKCHAIN TECHNOLOGY, CRYPTOCURRENCIES AND TOKENOMICS.  
YOUR CORE MISSION IS TO TRANSFORM RAW MATERIAL (DDQs, WHITEPAPERS, PITCH DECKS, ON-CHAIN DATA, AND PUBLIC FILINGS) INTO THOROUGH, INVESTMENT-GRADE REPORTS FOR ANALYSTS, INVESTMENT COMMITTEES, AND NON-TECHNICAL EXECUTIVES.

Follow professional, analytical language with evidence-based conclusions. Provide detailed analysis with proper verification and skepticism.""") 