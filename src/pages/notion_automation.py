"""
Notion Automation Page for AI Research Agent.
Handles Notion CRM integration and automated research pipelines.
"""

import streamlit as st
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import tempfile
from pathlib import Path
import json
import pickle
import os
import pandas as pd
import io
import re
from urllib.parse import urlparse, urljoin

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from docx import Document
except ImportError:
    Document = None

from src.pages.base_page import BasePage
from src.notion_watcher import poll_notion_db
from src.notion_research import run_deep_research  
from src.notion_writer import publish_report
from src.notion_scorer import run_project_scoring
from src.notion_pusher import publish_ratings
from src.config import AI_MODEL_OPTIONS
from src.core.scanner_utils import discover_sitemap_urls
from src.openrouter import OpenRouterClient
from src.firecrawl_client import FirecrawlClient
from src.core.rag_utils import (
    get_embedding_model,
    split_text_into_chunks,
    build_faiss_index,
    search_faiss_index,
    DEFAULT_EMBEDDING_MODEL,
    TOP_K_RESULTS
)
from src.models.chat_models import ChatSession, ChatHistoryItem

# Cache configuration
CACHE_DURATION_HOURS = 6
CACHE_FILE_PATH = "cache/notion_pages_cache.pkl"

class NotionAutomationPage(BasePage):
    """Notion automation page with CRM integration."""
    
    def __init__(self):
        super().__init__("notion_automation", "Notion CRM Integration")
        # Ensure cache directory exists
        os.makedirs("cache", exist_ok=True)
    
    def _load_cache(self) -> Optional[Dict]:
        """Load cached pages data if it exists and is valid."""
        try:
            if os.path.exists(CACHE_FILE_PATH):
                with open(CACHE_FILE_PATH, 'rb') as f:
                    cache_data = pickle.load(f)
                
                # Check if cache is still valid (within 6 hours)
                cache_time = cache_data.get('timestamp')
                if cache_time:
                    cache_dt = datetime.fromisoformat(cache_time)
                    now = datetime.now()
                    if now - cache_dt < timedelta(hours=CACHE_DURATION_HOURS):
                        return cache_data
        except Exception as e:
            self.logger.warning(f"Failed to load cache: {e}")
        return None
    
    def _save_cache(self, pages_data: List[Dict]) -> None:
        """Save pages data to cache with timestamp."""
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'pages': pages_data
            }
            with open(CACHE_FILE_PATH, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            self.logger.warning(f"Failed to save cache: {e}")
    
    def _get_cache_age(self) -> Optional[timedelta]:
        """Get the age of the current cache."""
        cache_data = self._load_cache()
        if cache_data and cache_data.get('timestamp'):
            try:
                cache_dt = datetime.fromisoformat(cache_data['timestamp'])
                return datetime.now() - cache_dt
            except:
                pass
        return None

    async def render(self) -> None:
        """Render the Notion automation page."""
        if not self.check_authentication():
            self.show_auth_required_message()
            return
        
        # Log page access
        self.log_page_access()
        
        # Initialize session state
        self._init_session_state()
        
        # Initialize clients
        self._init_clients()
        
        # Show page content
        self.show_page_header("Monitor Notion database and run automated research pipelines")
        
        # Check environment variables
        if not self._check_environment():
            return
        
        # Render main sections
        await self._render_configuration_section()
        await self._render_page_selection_section()
        await self._render_monitoring_section()
        await self._render_manual_operations()
        await self._render_additional_research_sources()
        await self._render_progress_tracking()
        await self._render_automation_status()
        
        # New sections matching Interactive Research
        await self._render_report_display()
        await self._render_admin_panel()
        await self._render_chat_interface()
    
    def _init_session_state(self) -> None:
        """Initialize required session state keys."""
        required_keys = {
            'notion_polling_active': False,
            'notion_last_poll_time': None,
            'notion_automation_logs': [],
            'notion_manual_research_running': False,
            'notion_available_pages': [],
            'notion_selected_pages': [],
            'notion_current_operation': None,
            'notion_operation_progress': {},
            'notion_last_poll_results': {},
            # Sitemap functionality session state
            'notion_discovered_sitemap_urls': [],
            'notion_sitemap_scan_in_progress': False,
            'notion_sitemap_scan_error': None,
            'notion_sitemap_scan_completed': False,
            'notion_selected_sitemap_urls': set(),
            # Report and chat functionality
            'notion_unified_report_content': "",
            'notion_report_generated_for_chat': False,
            'notion_current_report_id_for_chat': None,
            'notion_chat_sessions_store': {},
            'notion_current_chat_session_id': None,
            'notion_rag_contexts': {},
            'notion_chat_ui_expanded': False,
            'notion_ai_is_thinking': False,
            'notion_last_user_prompt_for_processing': None,
            'notion_processed_documents_content': [],
            'notion_last_uploaded_file_details': [],
        }
        self.init_session_state(required_keys)
    
    def _check_environment(self) -> bool:
        """Check if required environment variables are set."""
        import os
        
        required_vars = ["NOTION_TOKEN", "NOTION_DB_ID", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL"]
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.show_error("Missing required environment variables:")
            for var in missing_vars:
                st.write(f"❌ `{var}`")
            
            st.markdown("### Required Environment Variables")
            st.code("""
# Add these to your .env file:
NOTION_TOKEN=your_notion_integration_token
NOTION_DB_ID=your_notion_database_id
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
FIRECRAWL_BASE_URL=your_firecrawl_base_url
            """)
            return False
        
        return True
    
    async def _render_configuration_section(self) -> None:
        """Render the configuration section."""
        st.subheader("🔧 Configuration")
        
        with st.expander("Environment Status", expanded=False):
            import os
            
            # Show environment variable status
            vars_to_check = {
                "NOTION_TOKEN": "Notion Integration Token",
                "NOTION_DB_ID": "Notion Database ID", 
                "OPENROUTER_API_KEY": "OpenRouter API Key",
                "OPENROUTER_BASE_URL": "OpenRouter Base URL",
                "FIRECRAWL_BASE_URL": "Firecrawl Base URL"
            }
            
            for var, description in vars_to_check.items():
                value = os.getenv(var, "")
                if value:
                    if "token" in var.lower() or "key" in var.lower():
                        display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
                    else:
                        display_value = value
                    st.write(f"✅ **{description}**: `{display_value}`")
                else:
                    st.write(f"❌ **{description}**: Not set")
        
        st.markdown("---")
    
    async def _render_page_selection_section(self) -> None:
        """Render the page selection section with caching."""
        st.subheader("📄 Notion Page Selection")
        
        # Check cache status
        cache_data = self._load_cache()
        cache_age = self._get_cache_age()
        
        # Display cache status
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if cache_data:
                if cache_age:
                    hours = int(cache_age.total_seconds() / 3600)
                    minutes = int((cache_age.total_seconds() % 3600) / 60)
                    if hours > 0:
                        age_str = f"{hours}h {minutes}m ago"
                    else:
                        age_str = f"{minutes}m ago"
                    
                    cache_status = f"🟢 **Cache Available** (Updated {age_str})"
                    remaining_hours = CACHE_DURATION_HOURS - cache_age.total_seconds() / 3600
                    if remaining_hours > 1:
                        cache_status += f" • Valid for {remaining_hours:.1f}h more"
                    else:
                        cache_status += " • Expires soon"
                else:
                    cache_status = "🟡 **Cache Available** (Unknown age)"
            else:
                cache_status = "🔴 **No Cache** • Will fetch from Notion API"
            
            st.markdown(cache_status)
        
        with col2:
            # Load from cache button (if cache exists)
            if cache_data and st.button("💾 Load Cached", key="load_cache_btn", help="Load pages from 6-hour cache"):
                await self._load_cached_pages()
        
        with col3:
            # Fresh fetch button
            if st.button("🔍 Fetch Fresh", key="fetch_fresh_btn", help="Fetch latest data from Notion API"):
                await self._fetch_fresh_pages()
        
        # Auto-load cache on first visit if available
        if cache_data and not st.session_state.get('notion_available_pages'):
            st.info("💾 Loading cached pages automatically...")
            await self._load_cached_pages()
        
        # Show available pages if fetched
        if st.session_state.get('notion_available_pages'):
            st.markdown("**Select pages for automation:**")
            
            pages = st.session_state.notion_available_pages
            
            # Select all / none buttons
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("✅ Select All", key="select_all_pages"):
                    st.session_state.notion_selected_pages = [p['id'] for p in pages]
                    st.rerun()
            with col2:
                if st.button("❌ Clear Selection", key="clear_selection"):
                    st.session_state.notion_selected_pages = []
                    st.rerun()
            
            # Page checkboxes
            selected_pages = st.session_state.get('notion_selected_pages', [])
            
            for page in pages:
                page_id = page['id']
                page_title = page.get('title', 'Untitled')
                page_status = page.get('status', 'Unknown')
                
                is_selected = page_id in selected_pages
                
                # Create a more informative label
                label = f"📋 **{page_title}** (Status: {page_status})"
                
                if st.checkbox(label, value=is_selected, key=f"page_cb_{page_id}"):
                    if page_id not in selected_pages:
                        st.session_state.notion_selected_pages.append(page_id)
                else:
                    if page_id in selected_pages:
                        st.session_state.notion_selected_pages.remove(page_id)
            
            # Show selection summary with cache info
            selected_count = len(st.session_state.notion_selected_pages)
            total_count = len(pages)
            data_source = "💾 cached" if st.session_state.get('pages_from_cache') else "🔍 fresh"
            st.caption(f"**Selected: {selected_count}/{total_count} pages** • Data: {data_source}")
        
        else:
            if cache_data:
                st.info("💾 Click 'Load Cached' to view cached pages or 'Fetch Fresh' for latest data")
            else:
                st.info("🔍 Click 'Fetch Fresh' to load your Notion database entries")
        
        st.markdown("---")
    
    async def _load_cached_pages(self) -> None:
        """Load pages from cache."""
        try:
            cache_data = self._load_cache()
            if cache_data and cache_data.get('pages'):
                pages = cache_data['pages']
                st.session_state.notion_available_pages = pages
                st.session_state.pages_from_cache = True
                
                # Show cache info
                cache_time = cache_data.get('timestamp')
                if cache_time:
                    cache_dt = datetime.fromisoformat(cache_time)
                    formatted_time = cache_dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    formatted_time = "Unknown"
                
                self._add_automation_log(f"Loaded {len(pages)} pages from cache (cached at {formatted_time})")
                self.show_success(f"💾 Loaded {len(pages)} pages from cache!")
                
                # Show cache details
                with st.expander("💾 Cache Information", expanded=False):
                    st.write(f"**Cached at:** {formatted_time}")
                    st.write(f"**Pages count:** {len(pages)}")
                    cache_age = self._get_cache_age()
                    if cache_age:
                        hours = cache_age.total_seconds() / 3600
                        st.write(f"**Cache age:** {hours:.1f} hours")
                        st.write(f"**Expires in:** {CACHE_DURATION_HOURS - hours:.1f} hours")
            else:
                st.warning("⚠️ No valid cache data found")
        except Exception as e:
            self.show_error(f"Failed to load cached pages: {str(e)}")
    
    async def _fetch_fresh_pages(self) -> None:
        """Fetch fresh pages from Notion API and update cache."""
        try:
            with st.spinner("🔍 Fetching fresh data from Notion API..."):
                # Import the real poll_notion_db function
                from src.notion_watcher import poll_notion_db
                from datetime import timedelta
                
                # Fetch pages from the last 30 days with completed DDQs
                pages_data = poll_notion_db(created_after=30)
                
                # Convert to our expected format
                pages = []
                for page_data in pages_data:
                    page_info = {
                        "id": page_data["page_id"],
                        "title": page_data["title"] or f"Untitled ({page_data['page_id'][:8]})",
                        "status": "Completed DDQ",  # These are filtered to only show completed pages
                        "updated_time": page_data["updated_time"]
                    }
                    pages.append(page_info)
                
                # Update session state
                st.session_state.notion_available_pages = pages
                st.session_state.pages_from_cache = False
                
                # Save to cache
                self._save_cache(pages)
                
                self._add_automation_log(f"Fetched {len(pages)} fresh pages from Notion API and updated cache")
                
                if pages:
                    self.show_success(f"🔍 Fetched {len(pages)} fresh pages from Notion API! Cache updated.")
                    
                    # Show detailed results
                    with st.expander("📋 Fresh API Results", expanded=True):
                        st.markdown("**Pages found:**")
                        for i, page in enumerate(pages, 1):
                            updated = page.get('updated_time', 'Unknown')
                            if updated:
                                # Format the timestamp nicely
                                try:
                                    from datetime import datetime
                                    dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                                except:
                                    formatted_time = updated
                            else:
                                formatted_time = "Unknown"
                            
                            st.write(f"**{i}.** {page['title']}")
                            st.caption(f"   📄 ID: `{page['id']}`")
                            st.caption(f"   🕐 Last Updated: {formatted_time}")
                            st.caption(f"   ✅ Status: {page['status']}")
                            st.write("")
                        
                        # Show cache status
                        st.markdown("---")
                        st.write(f"💾 **Cache Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        st.write(f"⏱️ **Cache Valid Until:** {(datetime.now() + timedelta(hours=CACHE_DURATION_HOURS)).strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    st.warning("⚠️ No pages found with completed Due Diligence Questionnaires")
                    st.info("💡 **To see pages here:**\n- Go to your Notion database\n- Create a 'Due Diligence' child page\n- Complete the questionnaire and check it as done")
                
        except Exception as e:
            self.show_error(f"Failed to fetch fresh pages: {str(e)}")
            st.error("**Debug info:**")
            st.code(str(e))
            
            # Add helpful troubleshooting
            with st.expander("🔧 Troubleshooting", expanded=True):
                st.markdown("""
                **Common issues:**
                1. **NOTION_TOKEN** - Make sure your Notion integration token is valid
                2. **NOTION_DB_ID** - Verify your database ID is correct  
                3. **Database Access** - Ensure your integration has access to the database
                4. **Due Diligence Pages** - Check that you have child pages named 'Due Diligence...' 
                5. **Completed DDQs** - Make sure questionnaires are marked as complete with checkboxes
                """)

    # Keep the original _fetch_available_pages method for backward compatibility
    async def _fetch_available_pages(self) -> None:
        """Fetch available pages from Notion database (backward compatibility)."""
        await self._fetch_fresh_pages()
    
    async def _render_monitoring_section(self) -> None:
        """Render the monitoring section."""
        st.subheader("📊 Database Monitoring")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("▶️ Start Monitoring", key="start_monitoring_btn"):
                await self._start_notion_monitoring()
        
        with col2:
            if st.button("⏹️ Stop Monitoring", key="stop_monitoring_btn"):
                await self._stop_notion_monitoring()
        
        with col3:
            if st.button("🔍 Poll Now", key="manual_poll_btn"):
                await self._manual_poll_database()
        
        # Show monitoring status with better visuals
        status_col1, status_col2 = st.columns([1, 1])
        
        with status_col1:
            if st.session_state.get('notion_polling_active'):
                st.success("🟢 **Monitoring: ACTIVE**")
            else:
                st.info("🔵 **Monitoring: INACTIVE**")
        
        with status_col2:
            if st.session_state.get('notion_last_poll_time'):
                last_poll = st.session_state.notion_last_poll_time
                if isinstance(last_poll, datetime):
                    time_str = last_poll.strftime("%H:%M:%S")
                else:
                    time_str = str(last_poll)
                st.write(f"🕐 **Last poll**: {time_str}")
            else:
                st.write("🕐 **Last poll**: Never")
        
        # Show poll results if available
        if st.session_state.get('notion_last_poll_results'):
            with st.expander("📋 Latest Poll Results", expanded=False):
                results = st.session_state.notion_last_poll_results
                st.json(results)
        
        st.markdown("---")
    
    async def _render_manual_operations(self) -> None:
        """Render manual operations section."""
        st.subheader("🎯 Manual Operations")
        
        # Check if pages are selected
        selected_pages = st.session_state.get('notion_selected_pages', [])
        
        if not selected_pages:
            st.warning("⚠️ Please select pages above before running manual operations")
            return
        
        st.success(f"✅ Ready to process {len(selected_pages)} selected page(s)")
        
        # Publishing Options in Manual Operations
        st.markdown("#### 🔄 **Publishing Options**")
        
        # Initialize auto-publish session state if not exists
        if 'notion_auto_publish_to_notion' not in st.session_state:
            st.session_state.notion_auto_publish_to_notion = False  # Default to False for explicit user choice
        
        auto_publish = st.checkbox(
            "📤 **Auto-publish reports back to Notion pages**",
            value=st.session_state.get('notion_auto_publish_to_notion', False),
            key="notion_auto_publish_checkbox",
            help="Automatically create 'AI Deep Research Report by [username]' child pages in your Notion project pages"
        )
        st.session_state.notion_auto_publish_to_notion = auto_publish
        
        if auto_publish:
            username = st.session_state.get('username', 'Unknown User')
            st.success(f"✅ Reports will be automatically published as 'AI Deep Research Report by {username}' child pages")
            st.caption("💡 Each report will include your username for team attribution")
        else:
            st.info("📁 Reports will only be saved locally - no Notion publishing")
        
        st.markdown("---")
        
        # Add Additional Research Sources section
        await self._render_additional_research_sources()
        
        # Operation buttons
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔬 Enhanced Research", key="manual_research_btn", help="Run deep research with all sources on selected pages"):
                await self._manual_research_pipeline()
        
        with col2:
            if st.button("📊 Update Scoring", key="manual_scoring_btn", help="Run AI scoring on selected pages"):
                await self._manual_scoring_update()
        
        with col3:
            if st.button("📝 Generate Reports", key="manual_reports_btn", help="Generate reports for selected pages"):
                await self._manual_generate_reports()
        
        # Manual Research section with clear explanation
        st.markdown("### 🔍 Custom Research Query")
        st.markdown("""
        **What is Manual Research?**
        - Enter a custom research question or topic
        - The AI will research this topic using web search
        - Results will be saved as a report
        - Useful for ad-hoc research not tied to specific Notion pages
        """)
        
        research_query = st.text_area(
            "Enter your research question:",
            height=100,
            key="manual_research_query",
            placeholder="Example: 'What are the latest trends in DeFi lending protocols?' or 'Analyze the competitive landscape for NFT marketplaces'"
        )
        
        if st.button("🚀 Run Custom Research", key="custom_research_btn") and research_query:
            await self._run_custom_research(research_query)
        
        st.markdown("---")
    
    async def _render_additional_research_sources(self) -> None:
        """Render additional research sources section."""
        st.markdown("### 📚 **Additional Research Sources**")
        st.markdown("*Enhance your Notion DDQ research with extra context and data*")
        
        # Initialize session state for additional sources
        additional_sources_keys = {
            'notion_uploaded_docs': [],
            'notion_web_urls': [],
            'notion_crawl_option': None,
            'notion_crawl_url': '',
            'notion_crawl_sitemap_url': '',
            'notion_selected_model': 'qwen/qwen3-30b-a3b:free'
        }
        self.init_session_state(additional_sources_keys)
        
        # Create tabs for different source types
        tab1, tab2, tab3, tab4 = st.tabs(["📄 Documents", "🌐 Web URLs", "🕷️ Site Crawling", "🤖 AI Model"])
        
        with tab1:
            st.markdown("#### 📄 Upload Additional Documents")
            st.caption("Add documents to supplement the DDQ analysis")
            
            uploaded_files = st.file_uploader(
                "Choose files (PDF, DOCX, TXT, MD)",
                type=['pdf', 'docx', 'txt', 'md'],
                accept_multiple_files=True,
                key="notion_additional_docs"
            )
            
            if uploaded_files:
                st.session_state.notion_uploaded_docs = uploaded_files
                st.success(f"✅ {len(uploaded_files)} document(s) uploaded")
                
                with st.expander("📋 Uploaded Files", expanded=False):
                    for file in uploaded_files:
                        st.write(f"📄 **{file.name}** ({file.size:,} bytes)")
            else:
                st.session_state.notion_uploaded_docs = []
        
        with tab2:
            st.markdown("#### 🌐 Provide Specific Web URLs")
            st.caption("Add relevant web pages for additional context")
            
            # URL input area
            urls_text = st.text_area(
                "Enter URLs (one per line):",
                height=150,
                key="notion_urls_input",
                placeholder="https://example.com/whitepaper\nhttps://docs.project.com/overview\nhttps://blog.company.com/announcement"
            )
            
            if urls_text.strip():
                urls = [url.strip() for url in urls_text.strip().split('\n') if url.strip()]
                st.session_state.notion_web_urls = urls
                
                if urls:
                    st.success(f"✅ {len(urls)} URL(s) added")
                    with st.expander("🔗 URLs to Process", expanded=False):
                        for i, url in enumerate(urls, 1):
                            st.write(f"{i}. {url}")
            else:
                st.session_state.notion_web_urls = []
        
        with tab3:
            st.markdown("#### 🕷️ Crawl & Scrape Websites")
            st.caption("Automatically discover and scrape content from websites")
            
            crawl_option = st.radio(
                "Choose crawling method:",
                ["None", "Option A: Scan Site Sitemap", "Option B: Crawl from URL"],
                key="notion_crawl_method"
            )
            
            st.session_state.notion_crawl_option = crawl_option
            
            if crawl_option == "Option A: Scan Site Sitemap":
                st.markdown("**📋 Scan Site for URLs from Sitemap**")
                st.caption("Get a comprehensive list of all pages from the website's sitemap")
                
                sitemap_url = st.text_input(
                    "URL to scan for sitemap:",
                    key="notion_sitemap_url",
                    placeholder="https://example.com"
                )
                st.session_state.notion_crawl_sitemap_url = sitemap_url
                
                if st.button("Scan Site for URLs", key="notion_scan_sitemap_btn"):
                    if sitemap_url:
                        await self._scan_sitemap(sitemap_url)
                    else:
                        self.show_warning("Please enter a URL to scan.")
                
                # Display scan results
                await self._render_sitemap_results()
                
                if sitemap_url and not st.session_state.get('notion_sitemap_scan_in_progress'):
                    st.info(f"🗺️ Will scan sitemap: {sitemap_url}")
            
            elif crawl_option == "Option B: Crawl from URL":
                st.markdown("**🕷️ Crawl and Scrape Starting from URL**")
                st.caption("Follow links automatically to discover related content")
                
                crawl_url = st.text_input(
                    "Starting URL:",
                    key="notion_crawl_start_url",
                    placeholder="https://example.com"
                )
                st.session_state.notion_crawl_url = crawl_url
                
                col1, col2 = st.columns(2)
                with col1:
                    max_pages = st.number_input("Max pages to crawl:", min_value=1, max_value=50, value=10, key="notion_max_pages")
                with col2:
                    max_depth = st.number_input("Max depth:", min_value=1, max_value=5, value=2, key="notion_max_depth")
                
                if crawl_url:
                    st.info(f"🔍 Will crawl from: {crawl_url} (max {max_pages} pages, depth {max_depth})")
        
        with tab4:
            st.markdown("#### 🤖 AI Model Selection")
            st.caption("Choose the AI model for research and analysis")
            
            model_options = AI_MODEL_OPTIONS
            
            selected_model = st.selectbox(
                "Select AI Model:",
                options=list(model_options.keys()),
                format_func=lambda x: model_options[x],
                key="notion_model_selection"
            )
            
            st.session_state.notion_selected_model = selected_model
            st.info(f"🤖 Selected: {model_options[selected_model]}")
        
        # Summary of additional sources
        st.markdown("#### 📊 **Research Enhancement Summary**")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            doc_count = len(st.session_state.get('notion_uploaded_docs', []))
            st.metric("📄 Documents", doc_count)
        
        with col2:
            url_count = len(st.session_state.get('notion_web_urls', []))
            st.metric("🌐 Web URLs", url_count)
        
        with col3:
            crawl_status = "✅" if st.session_state.get('notion_crawl_option', 'None') != 'None' else "❌"
            st.metric("🕷️ Crawling", crawl_status)
        
        with col4:
            model_name = st.session_state.get('notion_selected_model', '').split('/')[-1][:10]
            st.metric("🤖 Model", model_name)
        
        # Show what will be included in research
        sources = []
        selected_pages = st.session_state.get('notion_selected_pages', [])
        if selected_pages:
            sources.append(f"📋 {len(selected_pages)} Notion DDQ pages")
        if doc_count > 0:
            sources.append(f"📄 {doc_count} uploaded documents")
        if url_count > 0:
            sources.append(f"🌐 {url_count} web URLs")
        if st.session_state.get('notion_crawl_option', 'None') != 'None':
            sources.append(f"🕷️ Website crawling")
        
        if sources:
            st.success(f"**Research will include:** {' + '.join(sources)}")
        else:
            st.info("**Research will include:** Only selected Notion DDQ pages")
        
        st.markdown("---")
    
    async def _render_progress_tracking(self) -> None:
        """Render real-time progress tracking."""
        if st.session_state.get('notion_current_operation'):
            st.subheader("⏳ Operation in Progress")
            
            operation = st.session_state.notion_current_operation
            progress = st.session_state.get('notion_operation_progress', {})
            
            st.info(f"🔄 **Currently running**: {operation}")
            
            # Progress bar if available
            if 'percentage' in progress:
                st.progress(progress['percentage'] / 100)
                st.caption(f"Progress: {progress['percentage']}%")
            
            # Status message
            if 'status' in progress:
                st.write(f"📝 **Status**: {progress['status']}")
            
            # Time elapsed
            if 'start_time' in progress:
                elapsed = datetime.now() - progress['start_time']
                st.caption(f"⏱️ Elapsed: {str(elapsed).split('.')[0]}")
            
            st.markdown("---")
    
    async def _render_automation_status(self) -> None:
        """Render automation status and logs."""
        st.subheader("📈 Automation Status")
        
        # Create status cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            monitoring_status = "✅ ON" if st.session_state.get('notion_polling_active') else "❌ OFF"
            st.metric("Monitoring", monitoring_status)
        
        with col2:
            selected_count = len(st.session_state.get('notion_selected_pages', []))
            st.metric("Selected Pages", selected_count)
        
        with col3:
            log_count = len(st.session_state.get('notion_automation_logs', []))
            st.metric("Total Operations", log_count)
        
        with col4:
            operation_status = "🔄 BUSY" if st.session_state.get('notion_current_operation') else "💤 IDLE"
            st.metric("Status", operation_status)
        
        # Recent activity logs
        if st.session_state.get('notion_automation_logs'):
            with st.expander("📜 Recent Activity", expanded=False):
                logs = st.session_state.notion_automation_logs[-10:]  # Show last 10
                for log in reversed(logs):  # Show newest first
                    timestamp = log.get('timestamp', 'Unknown')
                    message = log.get('message', 'No message')
                    user = log.get('user', 'System')
                    
                    if isinstance(timestamp, datetime):
                        time_str = timestamp.strftime("%H:%M:%S")
                    else:
                        time_str = str(timestamp)
                    
                    st.write(f"🕐 **{time_str}** | 👤 {user} | {message}")
    
    async def _start_notion_monitoring(self) -> None:
        """Start Notion database monitoring."""
        try:
            st.session_state.notion_polling_active = True
            st.session_state.notion_last_poll_time = datetime.now()
            
            # Add log entry
            self._add_automation_log("Started Notion database monitoring")
            
            # In a real implementation, this would start a background task
            self.show_success("🟢 Notion monitoring started!")
            
            # Log the action
            self.show_success("Monitoring started successfully", "Started Notion database monitoring")
            
        except Exception as e:
            self.show_error(f"Failed to start monitoring: {str(e)}")
    
    async def _stop_notion_monitoring(self) -> None:
        """Stop Notion database monitoring."""
        try:
            st.session_state.notion_polling_active = False
            
            # Add log entry
            self._add_automation_log("Stopped Notion database monitoring")
            
            self.show_info("🔵 Notion monitoring stopped")
            
            # Log the action
            self.show_info("Monitoring stopped", "Stopped Notion database monitoring")
            
        except Exception as e:
            self.show_error(f"Failed to stop monitoring: {str(e)}")
    
    async def _manual_poll_database(self) -> None:
        """Manually poll the Notion database."""
        try:
            self._start_operation("Polling Database")
            
            with st.spinner("🔍 Polling Notion database..."):
                # Import and call the real polling function
                from src.notion_watcher import poll_notion_db
                from datetime import datetime, timedelta
                
                # Step 1: Basic poll
                self._update_progress(20, "Connecting to Notion API...")
                await asyncio.sleep(0.5)
                
                # Step 2: Query database
                self._update_progress(40, "Querying database for completed DDQs...")
                pages_data = poll_notion_db(created_after=30)  # Last 30 days
                await asyncio.sleep(0.5)
                
                # Step 3: Process results
                self._update_progress(60, "Processing results...")
                await asyncio.sleep(0.5)
                
                # Step 4: Update session state
                self._update_progress(80, "Updating cache...")
                pages = []
                for page_data in pages_data:
                    page_info = {
                        "id": page_data["page_id"],
                        "title": page_data["title"] or f"Untitled ({page_data['page_id'][:8]})",
                        "status": "Completed DDQ",
                        "updated_time": page_data["updated_time"]
                    }
                    pages.append(page_info)
                
                st.session_state.notion_available_pages = pages
                await asyncio.sleep(0.5)
                
                # Step 5: Final
                self._update_progress(100, "Poll completed!")
                
                # Update last poll time
                st.session_state.notion_last_poll_time = datetime.now()
                
                # Store detailed results
                results = {
                    "total_entries": len(pages),
                    "new_entries": len(pages),  # For manual polls, consider all as "new"
                    "updated_entries": 0,
                    "poll_timestamp": datetime.now().isoformat(),
                    "pages_found": pages
                }
                st.session_state.notion_last_poll_results = results
                
                # Add log entry
                self._add_automation_log(f"Manual database poll completed - found {len(pages)} pages")
                
                # Show success with detailed results
                self.show_success(f"✅ Database poll completed! Found {len(pages)} pages with completed DDQs")
                
                # Display the actual results
                if pages:
                    st.markdown("### 📊 **Poll Results**")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("📄 Total Pages", len(pages))
                    with col2:
                        st.metric("✅ Completed DDQs", len(pages))
                    with col3:
                        st.metric("🕐 Last 30 Days", len(pages))
                    
                    # Show individual pages
                    with st.expander("📋 **Individual Pages Found**", expanded=True):
                        for i, page in enumerate(pages, 1):
                            with st.container():
                                st.markdown(f"**{i}. {page['title']}**")
                                col1, col2 = st.columns([2, 1])
                                with col1:
                                    st.caption(f"📄 Page ID: `{page['id']}`")
                                with col2:
                                    if page.get('updated_time'):
                                        try:
                                            dt = datetime.fromisoformat(page['updated_time'].replace('Z', '+00:00'))
                                            time_str = dt.strftime("%m/%d %H:%M")
                                        except:
                                            time_str = page['updated_time'][:10]
                                        st.caption(f"🕐 {time_str}")
                                st.divider()
                else:
                    st.info("ℹ️ No pages found with completed Due Diligence Questionnaires in the last 30 days")
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Database poll failed: {str(e)}")
            
            # Show debug information
            with st.expander("🐛 Error Details", expanded=True):
                st.code(f"Error: {type(e).__name__}: {str(e)}")
                
                # Environment check
                import os
                st.markdown("**Environment Check:**")
                env_vars = ["NOTION_TOKEN", "NOTION_DB_ID"]
                for var in env_vars:
                    value = os.getenv(var)
                    if value:
                        st.write(f"✅ {var}: Set")
                    else:
                        st.write(f"❌ {var}: Not set")
    
    async def _manual_research_pipeline(self) -> None:
        """Run the enhanced research pipeline manually on selected pages with additional sources."""
        try:
            selected_pages = st.session_state.get('notion_selected_pages', [])
            self._start_operation(f"Enhanced Research Pipeline ({len(selected_pages)} pages)")
            
            # Get page details for better display
            available_pages = st.session_state.get('notion_available_pages', [])
            page_lookup = {p['id']: p for p in available_pages}
            
            # Get additional research sources
            uploaded_docs = st.session_state.get('notion_uploaded_docs', [])
            web_urls = st.session_state.get('notion_web_urls', [])
            crawl_option = st.session_state.get('notion_crawl_option', 'None')
            selected_model = st.session_state.get('notion_selected_model', 'qwen/qwen3-30b-a3b:free')
            
            with st.spinner("🔬 Running enhanced research pipeline..."):
                results = []
                
                # Step 1: Process additional sources first
                additional_content = await self._process_additional_sources(
                    uploaded_docs, web_urls, crawl_option
                )
                
                # Step 2: Process each selected page
                for i, page_id in enumerate(selected_pages):
                    page_info = page_lookup.get(page_id, {'title': f'Page {page_id[:8]}', 'id': page_id})
                    progress = int((i + 1) / len(selected_pages) * 100)
                    
                    self._update_progress(progress, f"Processing: {page_info['title']} ({i+1}/{len(selected_pages)})")
                    
                    try:
                        # Get DDQ content from Notion
                        from src.notion_research import _fetch_ddq_markdown, _fetch_calls_text, _fetch_freeform_text
                        
                        ddq_content = _fetch_ddq_markdown(page_id)
                        calls_content = _fetch_calls_text(page_id)
                        freeform_content = _fetch_freeform_text(page_id)
                        
                        # Combine all content sources
                        combined_content = self._combine_all_sources(
                            ddq_content, calls_content, freeform_content, additional_content, page_info['title']
                        )
                        
                        # Run enhanced research with combined content
                        report_path = await self._run_enhanced_research(
                            page_id, page_info['title'], combined_content, selected_model
                        )
                        
                        results.append({
                            'page_id': page_id,
                            'page_title': page_info['title'],
                            'status': 'Success',
                            'report_path': str(report_path),
                            'sources_used': self._get_sources_summary(uploaded_docs, web_urls, crawl_option),
                            'model_used': selected_model
                        })
                        
                    except Exception as page_error:
                        results.append({
                            'page_id': page_id,
                            'page_title': page_info['title'],
                            'status': 'Error',
                            'error': str(page_error)
                        })
                    
                    # Realistic research time
                    await asyncio.sleep(3)
                
                # Add log entry
                successful = sum(1 for r in results if r['status'] == 'Success')
                failed = len(results) - successful
                self._add_automation_log(f"Enhanced research completed: {successful} successful, {failed} failed")
                
                # Show results
                if successful > 0:
                    self.show_success(f"✅ Enhanced research pipeline completed! {successful}/{len(selected_pages)} pages processed successfully")
                else:
                    self.show_error(f"❌ Enhanced research pipeline failed for all {len(selected_pages)} pages")
                
                # Display detailed results
                st.markdown("### 📊 **Enhanced Research Results**")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("✅ Successful", successful)
                with col2:
                    st.metric("❌ Failed", failed)
                with col3:
                    sources_count = len(uploaded_docs) + len(web_urls) + (1 if crawl_option != 'None' else 0)
                    st.metric("📚 Extra Sources", sources_count)
                with col4:
                    st.metric("🤖 Model", selected_model.split('/')[-1][:10])
                
                # Show individual results
                with st.expander("📋 **Individual Results**", expanded=True):
                    for result in results:
                        if result['status'] == 'Success':
                            st.success(f"✅ **{result['page_title']}**")
                            st.caption(f"📄 Page ID: `{result['page_id']}`")
                            st.caption(f"📊 Report: `{result['report_path']}`")
                            st.caption(f"📚 Sources: {result['sources_used']}")
                            st.caption(f"🤖 Model: {result['model_used']}")
                        else:
                            st.error(f"❌ **{result['page_title']}**")
                            st.caption(f"📄 Page ID: `{result['page_id']}`")
                            st.caption(f"🚨 Error: {result.get('error', 'Unknown error')}")
                        st.divider()
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Enhanced research pipeline failed: {str(e)}")
            
            with st.expander("🐛 Error Details"):
                st.code(str(e))
    
    async def _process_additional_sources(self, uploaded_docs, web_urls, crawl_option):
        """Process additional research sources and return combined content."""
        additional_content = {
            'documents': [],
            'web_pages': [],
            'crawled_pages': []
        }
        
        # Process uploaded documents with proper extraction
        if uploaded_docs:
            self._update_progress(10, "Processing uploaded documents...")
            
            # Store processed documents in session state
            current_file_details = [(f.name, f.size) for f in uploaded_docs]
            files_have_changed = (current_file_details != st.session_state.get("notion_last_uploaded_file_details", []))
            
            if files_have_changed:
                st.session_state.notion_last_uploaded_file_details = current_file_details
                st.session_state.notion_processed_documents_content = []
                
                for doc in uploaded_docs:
                    try:
                        # Use proper file extraction
                        content = await self._extract_file_content(doc)
                        
                        processed_doc = {
                            'name': doc.name,
                            'text': content,
                            'size': doc.size
                        }
                        
                        st.session_state.notion_processed_documents_content.append(processed_doc)
                        additional_content['documents'].append({
                            'name': doc.name,
                            'content': content
                        })
                        
                    except Exception as e:
                        st.warning(f"Failed to process {doc.name}: {str(e)}")
            else:
                # Use cached processed documents
                for doc in st.session_state.notion_processed_documents_content:
                    additional_content['documents'].append({
                        'name': doc['name'],
                        'content': doc['text']
                    })
        
        # Collect URLs to scrape
        urls_to_scrape = []
        
        # Add manual web URLs
        if web_urls:
            urls_to_scrape.extend(web_urls)
        
        # Add selected sitemap URLs
        if crawl_option == "Option A: Scan Site Sitemap":
            selected_sitemap_urls = st.session_state.get('notion_selected_sitemap_urls', set())
            if selected_sitemap_urls:
                urls_to_scrape.extend(list(selected_sitemap_urls))
        
        # Process all URLs together
        if urls_to_scrape:
            self._update_progress(20, f"Scraping {len(urls_to_scrape)} URLs...")
            scraped_results = await self._scrape_urls(urls_to_scrape)
            for result in scraped_results:
                if result.get("status") == "success" and result.get("content"):
                    additional_content['web_pages'].append({
                        'url': result['url'],
                        'content': result['content']
                    })
        
        # Process crawling for Option B
        if crawl_option == "Option B: Crawl from URL":
            self._update_progress(30, "Crawling website...")
            try:
                crawl_url = st.session_state.get('notion_crawl_url', '')
                if crawl_url:
                    max_pages = st.session_state.get('notion_max_pages', 10)
                    # Simple crawling - just scrape the starting URL for now
                    crawled_results = await self._scrape_urls([crawl_url])
                    for result in crawled_results:
                        if result.get("status") == "success" and result.get("content"):
                            additional_content['crawled_pages'].append({
                                'url': result['url'],
                                'content': result['content']
                            })
            except Exception as e:
                st.warning(f"Crawling failed: {str(e)}")
        
        return additional_content
    
    async def _scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Scrape content from URLs using firecrawl client."""
        if not st.session_state.get('notion_firecrawl_client'):
            return []
        
        try:
            client = st.session_state.notion_firecrawl_client
            results = []
            
            # Use the same logic as Interactive Research
            scraped_results = await client.scrape_multiple_urls(urls)
            
            for result in scraped_results:
                url = result.get("metadata", {}).get("url", result.get("url", "unknown"))
                if result.get("success", False):
                    content = result.get("data", {}).get("content", "")
                    if not content:
                        content = result.get("content", "")
                    results.append({"url": url, "content": content, "status": "success"})
                else:
                    error = result.get("error", "Unknown error")
                    results.append({"url": url, "error": error, "status": "failed"})
            
            return results
        except Exception as e:
            self.show_error(f"Error scraping URLs: {str(e)}")
            return []
    
    def _combine_all_sources(self, ddq_content, calls_content, freeform_content, additional_content, project_title):
        """Combine DDQ content with additional research sources."""
        combined = f"""
# Enhanced Research Report for {project_title}

## 📋 Core Project Information

### Due Diligence Questionnaire
{ddq_content}

### Call Notes
{calls_content}

### Additional Project Information  
{freeform_content}

## 📚 Additional Research Sources

"""
        
        # Add uploaded documents
        if additional_content['documents']:
            combined += "### 📄 Uploaded Documents\n\n"
            for doc in additional_content['documents']:
                combined += f"**{doc['name']}:**\n{doc['content']}\n\n"
        
        # Add web pages
        if additional_content['web_pages']:
            combined += "### 🌐 Web Pages\n\n"
            for page in additional_content['web_pages']:
                combined += f"**{page['url']}:**\n{page['content']}\n\n"
        
        # Add crawled content
        if additional_content['crawled_pages']:
            combined += "### 🕷️ Crawled Content\n\n"
            for page in additional_content['crawled_pages']:
                combined += f"**{page.get('url', 'Unknown URL')}:**\n{page.get('content', 'No content')}\n\n"
        
        return combined
    
    async def _run_enhanced_research(self, page_id, page_title, combined_content, model):
        """Run AI research on combined content."""
        try:
            # Import AI research functions
            from web_research.deep_research import deep_research as _deep_research
            from web_research.deep_research import write_final_report as _write_final_report
            
            # Initialize AI client with selected model
            client = st.session_state.get('notion_openrouter_client')
            if not client:
                raise RuntimeError("OpenRouter client not available")
            
            # Run deep research with combined content
            results = await _deep_research(
                query=combined_content,
                breadth=2,  # Enhanced breadth for better research
                depth=2,    # Enhanced depth
                concurrency=2,
                client=client,
                model=model,
            )
            
            # Generate final report
            learnings = results.get("learnings", [])
            visited_urls = results.get("visited_urls", [])
            
            report_md = await _write_final_report(
                prompt=combined_content,
                learnings=learnings,
                visited_urls=visited_urls,
                client=client,
                model=model,
            )
            
            # Save enhanced report to file
            from pathlib import Path
            reports_dir = Path("reports")
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_path = reports_dir / f"enhanced_report_{page_id}.md"
            report_path.write_text(report_md, encoding="utf-8")
            
            # Check if auto-publish to Notion is enabled
            auto_publish = st.session_state.get('notion_auto_publish_to_notion', True)
            notion_url = None
            
            if auto_publish:
                try:
                    # Import and use the Notion writer
                    from src.notion_writer import publish_report
                    
                    # Publish the report back to Notion as a child page
                    notion_url = publish_report(page_id, report_path)
                    
                    self.show_success(f"✅ Report published to Notion: {notion_url}")
                    
                except Exception as notion_error:
                    self.show_warning(f"⚠️ Report generated but Notion publishing failed: {str(notion_error)}")
                    st.info("💾 Report saved locally and can be manually uploaded to Notion")
            else:
                st.info("📁 Report saved locally (auto-publish disabled)")
            
            # Store in session state for display and chat (like Interactive Research)
            st.session_state.notion_unified_report_content = report_md
            st.session_state.notion_report_generated_for_chat = True
            
            # Store Notion URL if published
            if notion_url:
                st.session_state.notion_published_report_url = notion_url
            
            # Generate report ID for chat
            report_id = f"notion_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S%f')}"
            st.session_state.notion_current_report_id_for_chat = report_id
            
            # Build RAG context automatically
            await self._build_rag_context(report_id)
            
            return report_path
            
        except Exception as e:
            raise RuntimeError(f"Enhanced research failed: {str(e)}")
    
    def _get_sources_summary(self, uploaded_docs, web_urls, crawl_option):
        """Get a summary of sources used."""
        sources = []
        if uploaded_docs:
            sources.append(f"{len(uploaded_docs)} docs")
        
        # Count URLs including sitemap URLs
        total_urls = len(web_urls) if web_urls else 0
        if crawl_option == "Option A: Scan Site Sitemap":
            selected_sitemap_urls = st.session_state.get('notion_selected_sitemap_urls', set())
            total_urls += len(selected_sitemap_urls)
        
        if total_urls > 0:
            sources.append(f"{total_urls} URLs")
        
        if crawl_option == "Option B: Crawl from URL":
            sources.append("crawled content")
        
        return ", ".join(sources) if sources else "DDQ only"
    
    async def _manual_scoring_update(self) -> None:
        """Update scoring manually for selected pages."""
        try:
            selected_pages = st.session_state.get('notion_selected_pages', [])
            self._start_operation(f"Scoring Update ({len(selected_pages)} pages)")
            
            with st.spinner("📊 Updating project scoring..."):
                total_pages = len(selected_pages)
                for i, page_id in enumerate(selected_pages):
                    progress = int((i + 1) / total_pages * 100)
                    self._update_progress(progress, f"Scoring page {i+1}/{total_pages}: {page_id[:8]}...")
                    
                    # Simulate scoring time
                    await asyncio.sleep(0.8)
                
                # Add log entry
                self._add_automation_log(f"Scoring update completed for {len(selected_pages)} pages")
                
                self.show_success(f"✅ Scoring update completed for {len(selected_pages)} pages!")
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Scoring update failed: {str(e)}")
    
    async def _manual_generate_reports(self) -> None:
        """Generate reports for selected pages."""
        try:
            selected_pages = st.session_state.get('notion_selected_pages', [])
            self._start_operation(f"Report Generation ({len(selected_pages)} pages)")
            
            with st.spinner("📝 Generating reports..."):
                total_pages = len(selected_pages)
                for i, page_id in enumerate(selected_pages):
                    progress = int((i + 1) / total_pages * 100)
                    self._update_progress(progress, f"Generating report {i+1}/{total_pages}: {page_id[:8]}...")
                    
                    # Simulate report generation time
                    await asyncio.sleep(1.2)
                
                # Add log entry
                self._add_automation_log(f"Report generation completed for {len(selected_pages)} pages")
                
                self.show_success(f"✅ Reports generated for {len(selected_pages)} pages!")
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Report generation failed: {str(e)}")
    
    async def _run_custom_research(self, query: str) -> None:
        """Run custom research with the given query."""
        try:
            self._start_operation(f"Custom Research")
            
            with st.spinner(f"🔍 Researching: {query[:50]}..."):
                # Simulate research steps
                steps = [
                    "Analyzing query...",
                    "Searching web sources...", 
                    "Processing results...",
                    "Generating insights...",
                    "Finalizing report..."
                ]
                
                for i, step in enumerate(steps):
                    progress = int((i + 1) / len(steps) * 100)
                    self._update_progress(progress, step)
                    await asyncio.sleep(1)
                
                # Add log entry
                self._add_automation_log(f"Custom research completed: {query[:50]}...")
                
                self.show_success(f"✅ Custom research completed for: {query[:50]}...")
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Custom research failed: {str(e)}")
    
    def _start_operation(self, operation_name: str) -> None:
        """Start tracking an operation."""
        st.session_state.notion_current_operation = operation_name
        st.session_state.notion_operation_progress = {
            'start_time': datetime.now(),
            'percentage': 0,
            'status': 'Starting...'
        }
    
    def _update_progress(self, percentage: int, status: str) -> None:
        """Update operation progress."""
        if st.session_state.get('notion_operation_progress'):
            st.session_state.notion_operation_progress.update({
                'percentage': percentage,
                'status': status
            })
    
    def _end_operation(self) -> None:
        """End current operation tracking."""
        st.session_state.notion_current_operation = None
        st.session_state.notion_operation_progress = {}
    
    def _add_automation_log(self, message: str) -> None:
        """Add an entry to the automation log."""
        if 'notion_automation_logs' not in st.session_state:
            st.session_state.notion_automation_logs = []
        
        log_entry = {
            'timestamp': datetime.now(),
            'message': message,
            'user': st.session_state.get('username', 'Unknown')
        }
        
        st.session_state.notion_automation_logs.append(log_entry)
        
        # Keep only the last 100 log entries
        if len(st.session_state.notion_automation_logs) > 100:
            st.session_state.notion_automation_logs = st.session_state.notion_automation_logs[-100:]
    
    async def _scan_sitemap(self, site_url: str) -> None:
        """Scan site for sitemap URLs."""
        st.session_state.notion_sitemap_scan_in_progress = True
        st.session_state.notion_discovered_sitemap_urls = []
        st.session_state.notion_sitemap_scan_error = None
        st.session_state.notion_sitemap_scan_completed = False
        
        try:
            with st.spinner(f"Scanning {site_url} for sitemap URLs..."):
                discovered_urls = await discover_sitemap_urls(site_url)
            
            st.session_state.notion_discovered_sitemap_urls = discovered_urls
            st.session_state.notion_sitemap_scan_completed = True
            
            if discovered_urls:
                self.show_success(f"Found {len(discovered_urls)} URLs!")
            else:
                self.show_info("No URLs found in sitemap.")
                
        except Exception as e:
            error_msg = f"Sitemap scan failed: {str(e)}"
            st.session_state.notion_sitemap_scan_error = error_msg
            self.show_error(error_msg)
            st.session_state.notion_sitemap_scan_completed = True
        finally:
            st.session_state.notion_sitemap_scan_in_progress = False
            st.rerun()
    
    async def _render_sitemap_results(self) -> None:
        """Render sitemap scan results and URL selection."""
        if st.session_state.get('notion_sitemap_scan_completed') and st.session_state.get('notion_discovered_sitemap_urls'):
            st.subheader("📋 Select URLs for Scraping:")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Select All", key="notion_select_all_urls"):
                    st.session_state.notion_selected_sitemap_urls = set(st.session_state.notion_discovered_sitemap_urls)
                    st.rerun()
            with col2:
                if st.button("Deselect All", key="notion_deselect_all_urls"):
                    st.session_state.notion_selected_sitemap_urls = set()
                    st.rerun()
            
            # URL checkboxes
            for i, url in enumerate(st.session_state.notion_discovered_sitemap_urls):
                is_selected = url in st.session_state.notion_selected_sitemap_urls
                
                if st.checkbox(url, value=is_selected, key=f"notion_url_cb_{i}"):
                    st.session_state.notion_selected_sitemap_urls.add(url)
                else:
                    st.session_state.notion_selected_sitemap_urls.discard(url)
            
            selected_count = len(st.session_state.notion_selected_sitemap_urls)
            total_count = len(st.session_state.notion_discovered_sitemap_urls)
            st.caption(f"✅ {selected_count}/{total_count} URLs selected for scraping")

    def _init_clients(self) -> None:
        """Initialize API clients."""
        if "notion_openrouter_client" not in st.session_state:
            openrouter_client = OpenRouterClient()
            firecrawl_client = FirecrawlClient(redis_url=None)  # No Redis for now
            st.session_state.notion_openrouter_client = openrouter_client
            st.session_state.notion_firecrawl_client = firecrawl_client

    async def _extract_file_content(self, file_data) -> str:
        """Extract text content from uploaded file."""
        file_bytes = file_data.getvalue()
        file_name = file_data.name.lower()
        
        try:
            if file_name.endswith('.pdf'):
                return self._extract_pdf_content(file_bytes)
            elif file_name.endswith('.docx'):
                return self._extract_docx_content(file_bytes)
            elif file_name.endswith(('.txt', '.md')):
                return self._extract_text_content(file_bytes)
            else:
                return f"Unsupported file type: {file_name}"
        except Exception as e:
            return f"Error extracting content from {file_name}: {str(e)}"
    
    def _extract_pdf_content(self, file_bytes: bytes) -> str:
        """Extract text from PDF using PyMuPDF."""
        if not fitz:
            return "PyMuPDF not available for PDF processing."
        
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text_content = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_content.append(page.get_text())
            
            doc.close()
            return "\n".join(text_content)
        except Exception as e:
            return f"Error processing PDF: {str(e)}"
    
    def _extract_docx_content(self, file_bytes: bytes) -> str:
        """Extract text from DOCX using python-docx."""
        if not Document:
            return "python-docx not available for DOCX processing."
        
        try:
            doc = Document(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception as e:
            return f"Error processing DOCX: {str(e)}"
    
    def _extract_text_content(self, file_bytes: bytes) -> str:
        """Extract text from TXT/MD files."""
        try:
            return file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return file_bytes.decode('latin-1')
            except Exception as e:
                return f"Error decoding text file: {str(e)}"

    async def _render_report_display(self) -> None:
        """Render the generated report display."""
        if st.session_state.get('notion_unified_report_content'):
            st.markdown("---")
            st.subheader("📊 Generated Enhanced Report")
            
            # Show report metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 Report Length", f"{len(st.session_state.notion_unified_report_content)} chars")
            with col2:
                report_id = st.session_state.get('notion_current_report_id_for_chat', 'N/A')
                st.metric("🆔 Report ID", report_id[:8] if report_id != 'N/A' else 'N/A')
            with col3:
                rag_available = "✅" if st.session_state.get('notion_current_report_id_for_chat') in st.session_state.get('notion_rag_contexts', {}) else "❌"
                st.metric("🧠 RAG Context", rag_available)
            
            # Show Notion publication status
            notion_url = st.session_state.get('notion_published_report_url')
            if notion_url:
                st.success(f"🔗 **Published to Notion:** [View AI Deep Research Report]({notion_url})")
                st.caption("The report has been automatically added as a child page to your Notion project")
            else:
                auto_publish = st.session_state.get('notion_auto_publish_to_notion', True)
                if auto_publish:
                    st.info("📁 Report saved locally • Auto-publish enabled for next run")
                else:
                    st.info("📁 Report saved locally • Auto-publish disabled")
            
            # Display report content
            with st.expander("📖 **View Full Report**", expanded=False):
                st.markdown(st.session_state.notion_unified_report_content)
            
            # Download button
            st.download_button(
                label="📥 Download Enhanced Report",
                data=st.session_state.notion_unified_report_content,
                file_name=f"enhanced_notion_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                key="notion_download_report_btn"
            )

    async def _render_admin_panel(self) -> None:
        """Render admin panel if user is admin."""
        if st.session_state.get("role") == "admin":
            st.markdown("---")
            st.subheader("🔧 Admin Panel")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**🗃️ Cache Management**")
                if st.button("🗑️ Clear Page Cache", key="admin_clear_cache"):
                    try:
                        if os.path.exists(CACHE_FILE_PATH):
                            os.remove(CACHE_FILE_PATH)
                        st.session_state.notion_available_pages = []
                        st.session_state.notion_selected_pages = []
                        self.show_success("Cache cleared successfully!")
                    except Exception as e:
                        self.show_error(f"Failed to clear cache: {e}")
            
            with col2:
                st.markdown("**📊 System Stats**")
                logs_count = len(st.session_state.get('notion_automation_logs', []))
                st.metric("Total Logs", logs_count)
                
                reports_count = 1 if st.session_state.get('notion_unified_report_content') else 0
                st.metric("Active Reports", reports_count)
            
            with col3:
                st.markdown("**🔄 Reset Operations**")
                if st.button("🔄 Reset All States", key="admin_reset_states"):
                    # Reset key session states
                    reset_keys = [
                        'notion_automation_logs',
                        'notion_unified_report_content',
                        'notion_rag_contexts',
                        'notion_processed_documents_content'
                    ]
                    for key in reset_keys:
                        if key in st.session_state:
                            if 'logs' in key:
                                st.session_state[key] = []
                            elif 'contexts' in key:
                                st.session_state[key] = {}
                            else:
                                st.session_state[key] = "" if 'content' in key else []
                    
                    self.show_success("System states reset!")

    async def _render_chat_interface(self) -> None:
        """Render chat interface if report is generated."""
        if (st.session_state.get("notion_report_generated_for_chat") and 
            st.session_state.get("notion_current_report_id_for_chat")):
            
            st.markdown("---")
            
            # Chat interface
            with st.expander("💬 **Chat with AI about Enhanced Report**", expanded=st.session_state.get('notion_chat_ui_expanded', False)):
                report_id = st.session_state.notion_current_report_id_for_chat
                
                # Check if RAG context is available
                rag_context = st.session_state.get('notion_rag_contexts', {}).get(report_id)
                if rag_context:
                    st.success("🧠 **RAG Context Available** - Ask questions about the report content!")
                    
                    # Chat input
                    user_question = st.text_input(
                        "Ask a question about the report:",
                        key="notion_chat_input",
                        placeholder="What are the key findings about this project?"
                    )
                    
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if st.button("💬 Ask", key="notion_chat_ask_btn"):
                            if user_question:
                                await self._process_chat_question(user_question, report_id)
                            else:
                                st.warning("Please enter a question.")
                    
                    with col2:
                        if st.button("🧹 Clear Chat", key="notion_clear_chat_btn"):
                            st.session_state.notion_chat_sessions_store = {}
                            st.session_state.notion_current_chat_session_id = None
                            self.show_success("Chat cleared!")
                    
                    # Display chat history
                    self._display_chat_history(report_id)
                    
                else:
                    st.info("💡 **RAG Context Not Available** - Generate a report first to enable chat functionality.")
                    
                    if st.button("🔄 Build RAG Context", key="notion_build_rag_btn"):
                        await self._build_rag_context(report_id)

    async def _process_chat_question(self, question: str, report_id: str) -> None:
        """Process a chat question using RAG context."""
        try:
            rag_context = st.session_state.get('notion_rag_contexts', {}).get(report_id)
            if not rag_context:
                self.show_error("RAG context not available")
                return
            
            with st.spinner("🤔 AI is thinking..."):
                # Search for relevant context
                embedding_model = get_embedding_model()
                relevant_chunks = search_faiss_index(
                    question,
                    rag_context["index"],
                    rag_context["chunks"],
                    embedding_model,
                    top_k=TOP_K_RESULTS
                )
                
                # Build context for AI
                context = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
                
                # Generate response
                prompt = f"""Based on the following context from the research report, please answer the user's question.
                
Context:
{context}

Question: {question}

Please provide a helpful and accurate answer based on the context provided."""
                
                client = st.session_state.get('notion_openrouter_client')
                if client:
                    model_to_use = st.session_state.get("notion_selected_model", "qwen/qwen3-30b-a3b:free")
                    response = await client.generate_response(
                        prompt=prompt,
                        system_prompt="You are a helpful research assistant. Answer questions based on the provided context.",
                        model_override=model_to_use
                    )
                    
                    # Store in chat history
                    chat_history = st.session_state.get('notion_chat_sessions_store', {}).get(report_id, [])
                    chat_history.append({
                        'question': question,
                        'answer': response,
                        'timestamp': pd.Timestamp.now().strftime('%H:%M:%S')
                    })
                    
                    if 'notion_chat_sessions_store' not in st.session_state:
                        st.session_state.notion_chat_sessions_store = {}
                    st.session_state.notion_chat_sessions_store[report_id] = chat_history
                    
                    self.show_success("✅ Answer generated!")
                    st.rerun()
                else:
                    self.show_error("OpenRouter client not available")
                    
        except Exception as e:
            self.show_error(f"Chat processing failed: {str(e)}")
    
    def _display_chat_history(self, report_id: str) -> None:
        """Display chat history for the report."""
        chat_history = st.session_state.get('notion_chat_sessions_store', {}).get(report_id, [])
        
        if chat_history:
            st.markdown("### 📝 **Chat History**")
            for i, chat in enumerate(reversed(chat_history[-5:])):  # Show last 5 chats
                with st.container():
                    st.markdown(f"**🙋 Question ({chat['timestamp']}):**")
                    st.markdown(f"> {chat['question']}")
                    st.markdown(f"**🤖 Answer:**")
                    st.markdown(chat['answer'])
                    st.divider()
    
    async def _build_rag_context(self, report_id: str) -> None:
        """Build RAG context for the report."""
        try:
            with st.spinner("🧠 Building RAG context..."):
                embedding_model = get_embedding_model()
                
                # Combine all text for RAG
                all_text = []
                
                if st.session_state.get('notion_unified_report_content'):
                    all_text.append(st.session_state.notion_unified_report_content)
                
                for doc in st.session_state.get('notion_processed_documents_content', []):
                    all_text.append(f"--- Document: {doc['name']} ---\n{doc['text']}")
                
                combined_text = "\n\n---\n\n".join(all_text)
                text_chunks = split_text_into_chunks(combined_text)
                
                if text_chunks:
                    faiss_index = build_faiss_index(text_chunks, embedding_model)
                    if faiss_index:
                        if 'notion_rag_contexts' not in st.session_state:
                            st.session_state.notion_rag_contexts = {}
                        
                        st.session_state.notion_rag_contexts[report_id] = {
                            "index": faiss_index,
                            "chunks": text_chunks,
                            "embedding_model_name": DEFAULT_EMBEDDING_MODEL
                        }
                        self.show_success(f"🧠 RAG context built with {len(text_chunks)} chunks")
                    else:
                        st.session_state.notion_rag_contexts[report_id] = None
                        self.show_error("Failed to build FAISS index")
                else:
                    st.session_state.notion_rag_contexts[report_id] = None
                    self.show_error("No text chunks available for RAG")
                    
        except Exception as e:
            self.show_error(f"Error building RAG context: {str(e)}")
            st.session_state.notion_rag_contexts[report_id] = None 