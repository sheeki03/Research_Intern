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
from src.models.chat_models import ChatSession, ChatHistoryItem, ChatMessageInput, ChatMessageOutput, UserHistoryEntry
from src.services.user_history_service import user_history_service

# Cache configuration
CACHE_DURATION_HOURS = 12
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
                
                # Check if cache is still valid (within 12 hours)
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
        """Render the Notion automation page with improved UX/UI."""
        if not self.check_authentication():
            self.show_auth_required_message()
            return
        
        # Log page access
        self.log_page_access()
        
        # Initialize session state
        self._init_session_state()
        
        # Initialize clients
        self._init_clients()
        
        # Render sidebar with history
        self._render_sidebar_history()
        
        # Show page content
        self.show_page_header("🔗 Notion CRM Integration", 
                             subtitle="Connect with your Notion database to automate research workflows")
        
        # Custom CSS to make tab and expander text bigger
        st.markdown("""
        <style>
        /* Make tab text much bigger */
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            font-size: 24px !important;
            font-weight: 600 !important;
        }
        
        /* Make expander headers much bigger */
        .streamlit-expander .streamlit-expanderHeader p {
            font-size: 20px !important;
            font-weight: 600 !important;
        }
        
        /* Make radio button text bigger */
        .stRadio > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        
        /* Make checkbox text bigger */
        .stCheckbox > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        
        /* Make selectbox text bigger */
        .stSelectbox > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        
        /* Make file uploader text bigger */
        .stFileUploader > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        
        /* Make text input labels bigger */
        .stTextInput > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        
        /* Make text area labels bigger */
        .stTextArea > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        
        /* Make number input labels bigger */
        .stNumberInput > label > div[data-testid="stMarkdownContainer"] > p {
            font-size: 18px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Check environment variables
        if not self._check_environment():
            return
        
        # Render progress tracking at top if operation is running
        await self._render_progress_tracking()
        
        # Main workflow - always show
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown("## 🎯 **Main Workflow**")
        with col2:
            st.info("ℹ️", help="Complete automated research workflow: 1) Select Notion DDQ pages 2) Add extra sources (docs, URLs) 3) Run AI research and scoring. Everything gets saved back to Notion automatically.")
        
        await self._render_page_selection_section()
        await self._render_additional_research_sources()
        await self._render_manual_operations()
        
        # Results section - show automatically when research is complete
        if st.session_state.get('notion_unified_report_content'):
            st.markdown("---")
            st.markdown("## 📊 **Results & Reports**")
            await self._render_report_display()
            await self._render_scoring_results()
            await self._render_chat_interface()
        
        # Admin section - show for admin users
        if st.session_state.get("role") == "admin":
            st.markdown("---")
            st.markdown("## 👨‍💼 **Admin Controls**")
            await self._render_admin_panel()
    
    def _init_session_state(self) -> None:
        """Initialize required session state keys."""
        required_keys = {
            'notion_polling_active': False,
            'notion_last_poll_time': None,
            'notion_automation_logs': [],
            'notion_manual_research_running': False,
            'notion_available_pages': [],
            'notion_selected_pages': [],  # Keep for backward compatibility
            'notion_selected_page_id': None,  # New single page selection
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
            'notion_scraped_web_content': [],
            'notion_crawled_web_content': [],
            'notion_docsend_content': '',
            'notion_docsend_metadata': {},
        }
        self.init_session_state(required_keys)
    
    def _render_sidebar_history(self) -> None:
        """Render sidebar with user's chat history."""
        username = st.session_state.get('username')
        if not username:
            return
        
        with st.sidebar:
            st.markdown("## 📚 Your Recent Sessions")
            
            try:
                # Get user's recent chat sessions
                sessions = user_history_service.get_user_chat_sessions(username, 48)
                
                if not sessions:
                    st.info("No recent sessions found")
                    st.caption("Try generating a report and asking questions to create session history")
                    return
                
                st.markdown(f"*Last 48 hours ({len(sessions)} sessions)*")
                
                for session in sessions:
                    # Only show sessions from Notion Automation (filter by session_id pattern)
                    if not session['session_id'].startswith('streamlit_notion_'):
                        continue
                        
                    # Format timestamp
                    if isinstance(session['last_activity'], str):
                        last_activity = datetime.fromisoformat(session['last_activity'].replace('Z', '+00:00'))
                    else:
                        last_activity = session['last_activity']
                    
                    time_ago = self._format_time_ago(last_activity)
                    
                    # Create session preview
                    session_title = f"Report: {session['report_id'][:15]}..."
                    if len(session['report_id']) <= 15:
                        session_title = f"Report: {session['report_id']}"
                    
                    # Session container
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            if st.button(
                                f"💬 {session_title}",
                                key=f"notion_session_{session['session_id']}",
                                help=f"Resume session from {time_ago}",
                                use_container_width=True
                            ):
                                # Resume this session
                                self._resume_session(session)
                        
                        with col2:
                            st.markdown(f"<small>{time_ago}</small>", unsafe_allow_html=True)
                        
                        # Show session details
                        st.markdown(
                            f"<small>💬 {session['message_count']} messages</small>", 
                            unsafe_allow_html=True
                        )
                        st.markdown("---")
                
                # Refresh button
                if st.button("🔄 Refresh History", key="notion_refresh_history", use_container_width=True):
                    st.rerun()
                
                # Clear old history button
                if st.button("🧹 Clear Old History", key="notion_clear_old_history", use_container_width=True):
                    cleaned_count = user_history_service.cleanup_old_entries(48)
                    st.success(f"Cleaned {cleaned_count} old entries")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Error loading history: {str(e)}")
    
    def _format_time_ago(self, timestamp: datetime) -> str:
        """Format timestamp as 'time ago' string."""
        now = datetime.utcnow()
        if timestamp.tzinfo is not None:
            # Convert to UTC if timezone-aware
            timestamp = timestamp.replace(tzinfo=None)
        
        diff = now - timestamp
        
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"
    
    def _resume_session(self, session: Dict) -> None:
        """Resume a previous chat session."""
        try:
            # Set the current report ID for chat
            st.session_state.notion_current_report_id_for_chat = session['report_id']
            st.session_state.notion_report_generated_for_chat = True
            
            # Expand chat interface
            st.session_state.notion_chat_ui_expanded = True
            
            # Log session resume
            user_history_service.add_activity(
                UserHistoryEntry(
                    username=session['username'],
                    activity_type='session_resumed',
                    session_id=session['session_id'],
                    report_id=session['report_id'],
                    details={'action': 'resumed_from_sidebar', 'page': 'notion_automation'}
                )
            )
            
            st.success(f"📂 Resumed session for {session['report_id']}")
            st.rerun()
            
        except Exception as e:
            st.error(f"Error resuming session: {str(e)}")

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
    

    
    async def _render_page_selection_section(self) -> None:
        """Render the page selection section with improved UX."""
        
        # Step 1: Data Source - Simplified
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 📄 **Step 1: Load Notion Pages**")
            st.write("Get pages with completed Due Diligence Questionnaires")
        with col2:
            # Smart loading button
            cache_data = self._load_cache()
            if cache_data:
                if st.button("💾 Load Cached", key="load_cache_btn", help="Load from 6-hour cache"):
                    await self._load_cached_pages()
            
            if st.button("🔍 Fetch Fresh", key="fetch_fresh_btn", help="Get latest from Notion API"):
                await self._fetch_fresh_pages()
        
        # Cache status - simplified
        cache_age = self._get_cache_age()
        if cache_age:
            hours = cache_age.total_seconds() / 3600
            if hours < 1:
                st.write(f"💾 Cache: {int(cache_age.total_seconds() / 60)}m old")
            else:
                st.write(f"💾 Cache: {hours:.1f}h old")
        else:
            st.write("📡 No cache - click Fetch Fresh to load pages")
        
        # Auto-load cache on first visit if available
        if cache_data and not st.session_state.get('notion_available_pages'):
            st.info("💾 Loading cached pages automatically...")
            await self._load_cached_pages()
        
        # Step 2: Page Selection - Single Selection Only
        if st.session_state.get('notion_available_pages'):
            pages = st.session_state.notion_available_pages
            selected_page_id = st.session_state.get('notion_selected_page_id', None)
            
            st.markdown("### 📋 **Step 2: Select Page for Processing** (Single Selection)")
            
            # Clear selection control
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("❌ Clear", key="clear_selection"):
                    st.session_state.notion_selected_page_id = None
                    # Also clear the old multi-select for backward compatibility
                    st.session_state.notion_selected_pages = []
                    st.rerun()
            with col2:
                if selected_page_id:
                    selected_page = next((p for p in pages if p['id'] == selected_page_id), None)
                    page_title = selected_page['title'] if selected_page else 'Unknown'
                    st.metric("Selected Page", page_title)
                else:
                    st.metric("Selected Page", "None")
            
            # Radio button selection for single page
            page_options = ["None"] + [f"📋 {page.get('title', 'Untitled')}" for page in pages]
            page_ids = [None] + [page['id'] for page in pages]
            
            # Find current selection index
            current_index = 0
            if selected_page_id:
                try:
                    current_index = page_ids.index(selected_page_id)
                except ValueError:
                    current_index = 0
            
            selected_option_index = st.radio(
                "Choose one page:",
                range(len(page_options)),
                format_func=lambda x: page_options[x],
                index=current_index,
                key="page_radio_selection"
            )
            
            # Update session state based on radio selection
            new_selected_page_id = page_ids[selected_option_index]
            if new_selected_page_id != selected_page_id:
                st.session_state.notion_selected_page_id = new_selected_page_id
                # Update the old multi-select format for backward compatibility
                if new_selected_page_id:
                    st.session_state.notion_selected_pages = [new_selected_page_id]
                else:
                    st.session_state.notion_selected_pages = []
                st.rerun()
        
        else:
            st.markdown("#### 📋 **Step 2: Select Pages**")
            if cache_data:
                st.info("💾 Click 'Load Cached' above to view available pages")
            else:
                st.info("🔍 Click 'Fetch Fresh' above to load your Notion database")
        
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
                with st.expander("## 💾 Cache Information", expanded=False):
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
                    with st.expander("## 📋 Fresh API Results", expanded=True):
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
            with st.expander("## 🔧 Troubleshooting", expanded=True):
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
    

    
    async def _render_manual_operations(self) -> None:
        """Render streamlined manual operations section."""
        selected_pages = st.session_state.get('notion_selected_pages', [])
        
        # Step 4: Operations
        st.markdown("### ⚡ **Step 4: Run Operations**")
        st.write("**Workflow:** Enhanced Research → Project Scoring → Reports & Analysis")
        
        if not selected_pages:
            st.info("💡 Select a page above to enable operations")
            # Don't use st.stop() here as it prevents admin panel from rendering
            return
        
        # Quick settings
        col1, col2 = st.columns([2, 1])
        with col1:
            # Auto-publish settings for both Enhanced Research and Scoring
            auto_publish_research = st.checkbox(
                "**📤 Auto-publish Enhanced Research to Notion**",
                value=st.session_state.get('notion_auto_publish_to_notion', False),
                key="notion_auto_publish_checkbox",
                help="Create 'AI Deep Research Report by [username] (DD Month YYYY)' child pages"
            )
            st.session_state.notion_auto_publish_to_notion = auto_publish_research
            
            auto_publish_scoring = st.checkbox(
                "**📊 Auto-publish Project Scoring to Notion**", 
                value=st.session_state.get('notion_auto_publish_scoring', False),
                key="notion_auto_publish_scoring_main_checkbox",
                help="Create 'Project Scoring by [username] (DD Month YYYY)' child pages with results"
            )
            st.session_state.notion_auto_publish_scoring = auto_publish_scoring
        
        with col2:
            page_count = len(selected_pages)
            st.metric("Ready", f"{page_count} page{'s' if page_count != 1 else ''}")
        
        # Main operation buttons - prominent and clear
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🔬 Enhanced Research**")
            st.write("Step 1: Comprehensive analysis with extra sources")
            if st.button("🚀 Start Enhanced Research", key="manual_research_btn", type="primary"):
                await self._manual_research_pipeline()
        
        with col2:
            st.markdown("**📊 Project Scoring**")  
            st.write("Step 2: AI-powered investment evaluation")
            
            # Check if reports exist for selected pages
            has_reports, report_status = self._check_reports_exist_detailed(selected_pages)
            
            if not has_reports:
                st.button("📊 Start Scoring", key="manual_scoring_btn_disabled", disabled=True, 
                         help="Run Enhanced Research first to generate reports needed for scoring")
                st.info("💡 Run Enhanced Research first")
                
                # Debug info to help troubleshoot
                if st.checkbox("🔍 Show debug info", key="debug_reports"):
                    st.write("**Debug - Report Status:**")
                    for page_id, status in report_status.items():
                        st.write(f"📄 `{page_id}`: {status}")
                    
                    # Also show what files actually exist in reports directory
                    from pathlib import Path
                    reports_dir = Path("reports")
                    if reports_dir.exists():
                        st.write("**Files in reports directory:**")
                        report_files = list(reports_dir.glob("*.md"))
                        if report_files:
                            for file in sorted(report_files):
                                size = file.stat().st_size
                                st.write(f"📄 `{file.name}` ({size:,} bytes)")
                        else:
                            st.write("No .md files found")
                    else:
                        st.write("Reports directory does not exist")
            else:
                if st.button("📊 Start Scoring", key="manual_scoring_btn"):
                    await self._manual_scoring_update()
                
                # Show which reports were found
                st.success(f"✅ Found reports for {len([s for s in report_status.values() if 'Found' in s])} pages")
        

    
    async def _render_additional_research_sources(self) -> None:
        """Render streamlined additional research sources section."""
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown("### 📚 **Step 3: Add Extra Sources** (Optional)")
        with col2:
            st.info("ℹ️", help="Add extra information sources beyond the Notion DDQ data. Upload documents, specify web URLs to scrape, crawl websites automatically, or process DocSend decks. All sources get combined with DDQ data for comprehensive AI analysis.")
        
        st.write("Enhance research with documents, URLs, or website crawling")
        
        # Initialize session state for additional sources
        additional_sources_keys = {
            'notion_uploaded_docs': [],
            'notion_web_urls': [],
            'notion_crawl_option': None,
            'notion_crawl_url': '',
            'notion_crawl_sitemap_url': '',
            'notion_docsend_url': '',
            'notion_docsend_email': '',
            'notion_docsend_password': '',
            'notion_docsend_content': '',
            'notion_docsend_metadata': {},
            'notion_selected_model': 'qwen/qwen3-30b-a3b:free'
        }
        self.init_session_state(additional_sources_keys)
        
        # Collapsible additional sources
        with st.expander("# 📚 **Configure Additional Sources**", expanded=False):
            
            # Create tabs for different source types
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["## 📄 Documents", "## 🌐 Web URLs", "## 🕷️ Site Crawling", "## 📊 DocSend Decks", "## 🤖 AI Model"])
            
            with tab1:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown("### 📄 Upload Additional Documents")
                with col2:
                    st.info("ℹ️", help="Upload PDF, Word, text or markdown files containing relevant information. Examples: whitepapers, pitch decks, technical documentation, financial reports. Text is extracted and combined with DDQ data for analysis.")
                
                st.write("Add documents to supplement the DDQ analysis")
                
                uploaded_files = st.file_uploader(
                    "Choose files (PDF, DOCX, TXT, MD)",
                    type=['pdf', 'docx', 'txt', 'md'],
                    accept_multiple_files=True,
                    key="notion_additional_docs"
                )
                
                if uploaded_files:
                    st.session_state.notion_uploaded_docs = uploaded_files
                    st.success(f"✅ {len(uploaded_files)} document(s) uploaded")
                    
                    # Show uploaded files in a container instead of nested expander
                    with st.container():
                        st.markdown("**📋 Uploaded Files:**")
                        for file in uploaded_files:
                            st.write(f"📄 **{file.name}** ({file.size:,} bytes)")
                else:
                    st.session_state.notion_uploaded_docs = []
            
            with tab2:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown("### 🌐 Provide Specific Web URLs")
                with col2:
                    st.info("ℹ️", help="Enter specific web page URLs (one per line) to scrape for content. Examples: company websites, blog posts, documentation pages, news articles. The AI will extract text content from these pages for analysis.")
                
                st.write("Add relevant web pages for additional context")
                
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
                        # Show URLs in a container instead of nested expander
                        with st.container():
                            st.markdown("**🔗 URLs to Process:**")
                            for i, url in enumerate(urls, 1):
                                st.write(f"{i}. {url}")
                else:
                    st.session_state.notion_web_urls = []
            
            with tab3:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown("### 🕷️ Crawl & Scrape Websites")
                with col2:
                    st.info("ℹ️", help="Automatically discover and scrape multiple pages from websites. Option A scans the sitemap to find all pages, Option B crawls by following links. Great for exploring company websites, documentation sites, or blogs comprehensively.")
                
                st.write("Automatically discover and scrape content from websites")
                
                crawl_option = st.radio(
                    "Choose crawling method:",
                    ["None", "Option A: Scan Site Sitemap", "Option B: Crawl from URL"],
                    key="notion_crawl_method"
                )
                
                st.session_state.notion_crawl_option = crawl_option
                
                if crawl_option == "Option A: Scan Site Sitemap":
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown("**📋 Scan Site for URLs from Sitemap**")
                    with col2:
                        st.info("ℹ️", help="Finds all pages listed in the website's sitemap.xml file. This discovers the complete site structure including hidden or hard-to-find pages. More comprehensive than manual crawling.")
                    
                    st.write("Get a comprehensive list of all pages from the website's sitemap")
                    
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
                    
                    # Show sitemap scan results if scan completed (regardless of URLs found)
                    if st.session_state.get('notion_sitemap_scan_completed'):
                        discovered_urls = st.session_state.get('notion_discovered_sitemap_urls', [])
                        
                        if discovered_urls:
                            st.success(f"🗺️ Found {len(discovered_urls)} URLs from sitemap")
                            # Show first few URLs as preview (without expander to avoid nesting)
                            st.markdown("**📋 Sitemap URLs Preview:**")
                            for i, url in enumerate(discovered_urls[:5]):  # Show first 5
                                st.text(f"{i+1}. {url}")
                            if len(discovered_urls) > 5:
                                st.text(f"... and {len(discovered_urls) - 5} more URLs")
                        else:
                            st.warning(f"🗺️ Sitemap scan completed but found 0 URLs for {sitemap_url}")
                            st.info("💡 Try a different website or check if the site has a sitemap")
                    elif sitemap_url and not st.session_state.get('notion_sitemap_scan_in_progress'):
                        st.info(f"🗺️ Ready to scan sitemap: {sitemap_url}")
                
                elif crawl_option == "Option B: Crawl from URL":
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown("**🕷️ Crawl and Scrape Starting from URL**")
                    with col2:
                        st.info("ℹ️", help="Starts from a specific page and follows links to discover related content. You control the maximum number of pages and how deep to go. Good for focused exploration of specific site sections.")
                    
                    st.write("Follow links automatically to discover related content")
                    
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
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown("### 📊 DocSend Presentation Decks")
                with col2:
                    st.info("ℹ️", help="Extract text from DocSend presentation slides using advanced OCR technology. Provide the DocSend URL and access credentials to automatically process all slides. Perfect for pitch decks, investor presentations, or detailed project proposals.")
                
                st.write("Extract text from DocSend presentation slides using OCR")
                
                docsend_url = st.text_input(
                    "DocSend URL:",
                    key="notion_docsend_url",
                    placeholder="https://docsend.com/view/..."
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    docsend_email = st.text_input(
                        "Email:",
                        key="notion_docsend_email",
                        value=st.session_state.get('notion_docsend_email', ''),
                        placeholder="your@email.com"
                    )
                
                with col2:
                    docsend_password = st.text_input(
                        "Password (if required):",
                        key="notion_docsend_password",
                        type="password",
                        placeholder="Optional password"
                    )
                
                # Show status if DocSend content is cached
                if st.session_state.get('notion_docsend_content'):
                    docsend_metadata = st.session_state.get('notion_docsend_metadata', {})
                    slides_processed = docsend_metadata.get('processed_slides', 0)
                    total_slides = docsend_metadata.get('total_slides', 0)
                    processing_time = docsend_metadata.get('processing_time', 0)
                    
                    st.success(f"✅ DocSend deck processed: {slides_processed}/{total_slides} slides ({processing_time:.1f}s)")
                    
                    # Show DocSend details in a container instead of nested expander
                    with st.container():
                        st.markdown("**📋 DocSend Processing Details:**")
                        st.write(f"**URL:** {docsend_metadata.get('url', 'Unknown')}")
                        st.write(f"**Total slides:** {total_slides}")
                        st.write(f"**Slides with text:** {docsend_metadata.get('slides_with_text', 0)}")
                        st.write(f"**Total characters:** {docsend_metadata.get('total_characters', 0):,}")
                        st.write(f"**Processing time:** {processing_time:.1f} seconds")
                        
                        # Show preview of extracted content
                        content_preview = st.session_state.notion_docsend_content[:500]
                        st.text_area("Content preview:", content_preview, height=100, disabled=True)
                
                elif docsend_url:
                    st.info(f"📊 Will process DocSend deck: {docsend_url}")
                    if not docsend_email:
                        st.warning("⚠️ Email is required for DocSend access")
            
            with tab5:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown("### 🤖 AI Model Selection")
                with col2:
                    st.info("ℹ️", help="Choose which AI model to use for research and analysis. Different models have different capabilities and costs. Qwen 3 30B (free) provides good quality, while GPT-4 and Claude offer premium performance.")
                
                st.write("Choose the AI model for research and analysis")
                
                model_options = AI_MODEL_OPTIONS
                
                selected_model = st.selectbox(
                    "Select AI Model:",
                    options=list(model_options.keys()),
                    format_func=lambda x: model_options[x],
                    key="notion_model_selection"
                )
                
                st.session_state.notion_selected_model = selected_model
                st.info(f"🤖 Selected: {model_options[selected_model]}")
        
        # Show what will be included in research
        sources = []
        selected_pages = st.session_state.get('notion_selected_pages', [])
        doc_count = len(st.session_state.get('notion_uploaded_docs', []))
        url_count = len(st.session_state.get('notion_web_urls', []))
        
        if selected_pages:
            sources.append(f"📋 {len(selected_pages)} Notion DDQ pages")
        if doc_count > 0:
            sources.append(f"📄 {doc_count} uploaded documents")
        if url_count > 0:
            sources.append(f"🌐 {url_count} web URLs")
        if st.session_state.get('notion_crawl_option', 'None') != 'None':
            sources.append(f"🕷️ Website crawling")
        if st.session_state.get('notion_docsend_url'):
            sources.append(f"📊 DocSend deck")
        
        if sources:
            st.success(f"**Research will include:** {' + '.join(sources)}")
        else:
            st.info("**Research will include:** Only selected Notion DDQ pages")
        
        st.markdown("---")
    
    async def _render_progress_tracking(self) -> None:
        """Render compact progress tracking at top."""
        if st.session_state.get('notion_current_operation'):
            operation = st.session_state.notion_current_operation
            progress = st.session_state.get('notion_operation_progress', {})
            
            # Compact progress bar at top
            col1, col2 = st.columns([3, 1])
            with col1:
                if 'percentage' in progress:
                    st.progress(progress['percentage'] / 100)
                else:
                    st.progress(0.1)  # Show indeterminate progress
                    
                status_text = progress.get('status', 'Processing...')
                st.caption(f"🔄 {operation}: {status_text}")
            
            with col2:
                if 'start_time' in progress:
                    elapsed = datetime.now() - progress['start_time']
                    elapsed_str = str(elapsed).split('.')[0]
                    st.metric("⏱️ Elapsed", elapsed_str)
            
            st.markdown("---")
    
    async def _render_automation_status(self) -> None:
        """Render simplified automation status."""
        
        # Key metrics in a compact layout
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            monitoring_status = "✅ ON" if st.session_state.get('notion_polling_active') else "⚪ OFF"
            st.metric("Auto-Monitor", monitoring_status)
        
        with col2:
            selected_count = len(st.session_state.get('notion_selected_pages', []))
            st.metric("Pages Selected", selected_count)
        
        with col3:
            log_count = len(st.session_state.get('notion_automation_logs', []))
            st.metric("Operations Run", log_count)
        
        with col4:
            operation_status = "🔄 BUSY" if st.session_state.get('notion_current_operation') else "✅ READY"
            st.metric("System Status", operation_status)
        
        # Activity log - more compact
        if st.session_state.get('notion_automation_logs'):
            with st.expander("📜 **Recent Activity**", expanded=False):
                logs = st.session_state.notion_automation_logs[-5:]  # Show last 5
                for log in reversed(logs):  # Show newest first
                    timestamp = log.get('timestamp', 'Unknown')
                    message = log.get('message', 'No message')
                    user = log.get('user', 'System')
                    
                    if isinstance(timestamp, datetime):
                        time_str = timestamp.strftime("%H:%M")
                    else:
                        time_str = str(timestamp)
                    
                    st.caption(f"🕐 {time_str} | 👤 {user} | {message}")
        else:
            st.info("💡 No operations run yet - try Enhanced Research or Project Scoring")
    
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
            docsend_url = st.session_state.get('notion_docsend_url', '')
            docsend_email = st.session_state.get('notion_docsend_email', '')
            docsend_password = st.session_state.get('notion_docsend_password', '')
            selected_model = st.session_state.get('notion_selected_model', 'qwen/qwen3-30b-a3b:free')
            
            with st.spinner("🔬 Running enhanced research pipeline... (might be slow, please have patience)"):
                results = []
                
                # Step 1: Process additional sources first
                additional_content = await self._process_additional_sources(
                    uploaded_docs, web_urls, crawl_option, docsend_url, docsend_email, docsend_password
                )
                
                # Step 2: Process each selected page
                for i, page_id in enumerate(selected_pages):
                    page_info = page_lookup.get(page_id, {'title': f'Page {page_id[:8]}', 'id': page_id})
                    progress = int((i + 1) / len(selected_pages) * 100)
                    
                    self._update_progress(progress, f"Processing: {page_info['title']} ({i+1}/{len(selected_pages)})")
                    
                    try:
                        # Get DDQ content from Notion with proper null handling
                        from src.notion_research import _fetch_ddq_markdown, _fetch_calls_text, _fetch_freeform_text
                        
                        try:
                            ddq_content = _fetch_ddq_markdown(page_id)
                        except Exception as ddq_error:
                            self.show_warning(f"DDQ fetch failed for {page_info['title']}: {str(ddq_error)}")
                            ddq_content = "DDQ content not available."
                        
                        try:
                            calls_content = _fetch_calls_text(page_id)
                        except Exception as calls_error:
                            self.show_warning(f"Call notes fetch failed for {page_info['title']}: {str(calls_error)}")
                            calls_content = "Call notes not available."
                        
                        try:
                            freeform_content = _fetch_freeform_text(page_id)
                        except Exception as freeform_error:
                            self.show_warning(f"Freeform content fetch failed for {page_info['title']}: {str(freeform_error)}")
                            freeform_content = "Freeform content not available."
                        
                        # Ensure all content is strings, not None
                        ddq_content = ddq_content or "No DDQ content available."
                        calls_content = calls_content or "No call notes available."
                        freeform_content = freeform_content or "No freeform content available."
                        
                        # Combine all content sources
                        combined_content = self._combine_all_sources(
                            ddq_content, calls_content, freeform_content, additional_content, page_info['title']
                        )
                        
                        # Run enhanced research with combined content
                        report_path = await self._run_enhanced_research(
                            page_id, page_info['title'], combined_content, selected_model
                        )
                        
                        # Verify the file was actually created
                        if report_path.exists():
                            file_size = report_path.stat().st_size
                            results.append({
                                'page_id': page_id,
                                'page_title': page_info['title'],
                                'status': 'Success',
                                'report_path': str(report_path),
                                'file_size': file_size,
                                'sources_used': self._get_sources_summary(uploaded_docs, web_urls, crawl_option, docsend_url),
                                'model_used': selected_model,
                                'notion_url': st.session_state.get('notion_published_report_url'),
                                'auto_publish_enabled': st.session_state.get('notion_auto_publish_to_notion', False),
                                'username': st.session_state.get('username', 'Unknown User')
                            })
                        else:
                            results.append({
                                'page_id': page_id,
                                'page_title': page_info['title'],
                                'status': 'Error',
                                'error': f'Report generation completed but file not found at {report_path}'
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
                    st.info("📊 **Results automatically displayed below**")
                else:
                    self.show_error(f"❌ Enhanced research pipeline failed for all {len(selected_pages)} pages")
                
                # Display detailed results
                st.markdown("### 📊 **Enhanced Research Results**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("✅ Successful", successful)
                with col2:
                    st.metric("❌ Failed", failed)
                with col3:
                    sources_count = len(uploaded_docs) + len(web_urls) + (1 if crawl_option != 'None' else 0) + (1 if docsend_url else 0)
                    st.metric("📚 Extra Sources", sources_count)
                
                # Show individual results in a container instead of nested expander
                st.markdown("### 📋 **Individual Results**")
                with st.container():
                    for result in results:
                        if result['status'] == 'Success':
                            st.success(f"✅ **{result['page_title']}**")
                            st.caption(f"📄 Page ID: `{result['page_id']}`")
                            st.caption(f"📊 Report: `{result['report_path']}`")
                            
                            # Show file size if available
                            if result.get('file_size'):
                                st.caption(f"📁 File: {result['file_size']:,} bytes")
                            
                            st.caption(f"📚 Sources: {result['sources_used']}")
                            
                            # Show Notion publication status
                            if result.get('notion_url') and result.get('auto_publish_enabled'):
                                username = result.get('username', 'Unknown User')
                                st.caption(f"🔗 Notion: [AI Deep Research Report by {username}]({result['notion_url']})")
                            elif result.get('auto_publish_enabled'):
                                st.caption(f"📁 Notion: Publishing enabled but no URL available")
                            else:
                                st.caption(f"📁 Notion: Auto-publish disabled")
                                
                            # Show username attribution
                            username = result.get('username', 'Unknown User')
                            st.caption(f"👤 Created by: {username}")
                            
                        else:
                            st.error(f"❌ **{result['page_title']}**")
                            st.caption(f"📄 Page ID: `{result['page_id']}`")
                            st.caption(f"🚨 Error: {result.get('error', 'Unknown error')}")
                        st.divider()
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Enhanced research pipeline failed: {str(e)}")
            
            # Show error details in a container instead of nested expander
            st.markdown("**🐛 Error Details:**")
            st.code(str(e))
    
    async def _process_additional_sources(self, uploaded_docs, web_urls, crawl_option, 
                                         docsend_url='', docsend_email='', docsend_password=''):
        """Process additional research sources and return combined content."""
        additional_content = {
            'documents': [],
            'web_pages': [],
            'crawled_pages': [],
            'docsend_decks': []
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
        
        # Process DocSend deck if URL provided
        if docsend_url and docsend_email:
            self._update_progress(50, "Processing DocSend deck...")
            try:
                # Check if we already have cached DocSend content for this URL
                cached_url = st.session_state.get('notion_docsend_metadata', {}).get('url', '')
                if cached_url == docsend_url and st.session_state.get('notion_docsend_content'):
                    # Use cached content
                    docsend_content = st.session_state.notion_docsend_content
                    docsend_metadata = st.session_state.notion_docsend_metadata
                    
                    additional_content['docsend_decks'].append({
                        'url': docsend_url,
                        'content': docsend_content,
                        'metadata': docsend_metadata
                    })
                    
                    self._update_progress(60, f"Using cached DocSend content ({docsend_metadata.get('processed_slides', 0)} slides)")
                else:
                    # Process fresh DocSend content
                    from src.core.docsend_client import DocSendClient
                    
                    # Initialize DocSend client
                    tesseract_cmd = os.getenv('TESSERACT_CMD')
                    docsend_client = DocSendClient(tesseract_cmd=tesseract_cmd)
                    
                    # Process with thread-safe progress callback
                    import threading
                    progress_data = {'percentage': 0, 'status': 'Starting...'}
                    progress_lock = threading.Lock()
                    
                    def progress_callback(percentage, status):
                        """Thread-safe progress callback."""
                        try:
                            with progress_lock:
                                progress_data['percentage'] = percentage
                                progress_data['status'] = status
                            # Update progress in main thread context
                            self._update_progress(50 + int(percentage * 0.4), status)  # 50-90% range
                        except Exception:
                            pass  # Ignore any threading issues
                    
                    result = await docsend_client.fetch_docsend_async(
                        url=docsend_url,
                        email=docsend_email,
                        password=docsend_password if docsend_password else None,
                        progress_callback=progress_callback
                    )
                    
                    if result.get('success'):
                        docsend_content = result['content']
                        docsend_metadata = result['metadata']
                        
                        # Cache the results
                        st.session_state.notion_docsend_content = docsend_content
                        st.session_state.notion_docsend_metadata = docsend_metadata
                        
                        additional_content['docsend_decks'].append({
                            'url': docsend_url,
                            'content': docsend_content,
                            'metadata': docsend_metadata
                        })
                        
                        slides_processed = docsend_metadata.get('processed_slides', 0)
                        total_slides = docsend_metadata.get('total_slides', 0)
                        self._update_progress(90, f"DocSend processing complete: {slides_processed}/{total_slides} slides")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        st.warning(f"DocSend processing failed: {error_msg}")
                        self._update_progress(60, f"DocSend processing failed: {error_msg}")
                        
            except Exception as e:
                st.warning(f"DocSend processing error: {str(e)}")
                self._update_progress(60, f"DocSend error: {str(e)}")
        
        # Store scraped web content with improved chunked storage for chat use
        st.session_state.notion_scraped_web_content = self._process_scraped_content_for_storage(additional_content['web_pages'])
        st.session_state.notion_crawled_web_content = self._process_scraped_content_for_storage(additional_content['crawled_pages'])
        
        return additional_content
    
    def _process_scraped_content_for_storage(self, content_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Process scraped content into chunked storage with metadata for better AI analysis."""
        processed_content = []
        
        for item in content_list:
            url = item.get('url', 'Unknown URL')
            content = item.get('content', '')
            
            # Skip empty content
            if not content or len(content.strip()) < 50:
                continue
            
            # Create chunks of reasonable size (1000-2000 chars for better AI processing)
            chunks = self._create_semantic_chunks(content, max_chunk_size=1500)
            
            # Extract metadata from content
            metadata = self._extract_content_metadata(content, url)
            
            processed_item = {
                'url': url,
                'original_content': content,  # Keep full content for reference
                'chunks': chunks,
                'metadata': metadata,
                'chunk_count': len(chunks),
                'total_length': len(content),
                'processed_at': pd.Timestamp.now().isoformat()
            }
            
            processed_content.append(processed_item)
        
        return processed_content
    
    def _create_semantic_chunks(self, content: str, max_chunk_size: int = 1500) -> List[Dict[str, Any]]:
        """Create semantic chunks from content, preserving context and meaning."""
        chunks = []
        
        # Split by paragraphs first to maintain context
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        current_chunk = ""
        current_chunk_id = 0
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed max size, finalize current chunk
            if len(current_chunk) + len(paragraph) > max_chunk_size and current_chunk:
                chunks.append({
                    'chunk_id': current_chunk_id,
                    'text': current_chunk.strip(),
                    'length': len(current_chunk),
                    'topic_hints': self._extract_topic_hints(current_chunk)
                })
                current_chunk = ""
                current_chunk_id += 1
            
            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
        
        # Add final chunk if there's remaining content
        if current_chunk.strip():
            chunks.append({
                'chunk_id': current_chunk_id,
                'text': current_chunk.strip(),
                'length': len(current_chunk),
                'topic_hints': self._extract_topic_hints(current_chunk)
            })
        
        return chunks
    
    def _extract_content_metadata(self, content: str, url: str) -> Dict[str, Any]:
        """Extract useful metadata from scraped content."""
        import re
        from urllib.parse import urlparse
        
        # Parse URL for context
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Extract potential title (first line or heading)
        lines = content.split('\n')
        title = next((line.strip() for line in lines if line.strip() and len(line.strip()) > 10), "")[:100]
        
        # Extract key terms and topics
        content_lower = content.lower()
        keywords = []
        
        # Look for common crypto/business terms
        key_terms = [
            'token', 'blockchain', 'defi', 'nft', 'smart contract', 'governance',
            'roadmap', 'whitepaper', 'team', 'funding', 'partnership', 'api',
            'technical', 'documentation', 'security', 'audit', 'tokenomics'
        ]
        
        for term in key_terms:
            if term in content_lower:
                keywords.append(term)
        
        # Determine content type based on URL and content
        content_type = 'general'
        if 'docs' in url or 'documentation' in content_lower:
            content_type = 'documentation'
        elif 'blog' in url or 'news' in url:
            content_type = 'blog'
        elif 'whitepaper' in content_lower or 'paper' in url:
            content_type = 'whitepaper'
        elif 'team' in content_lower or 'about' in url:
            content_type = 'team'
        
        return {
            'domain': domain,
            'title': title,
            'content_type': content_type,
            'keywords': keywords[:10],  # Limit to top 10
            'estimated_read_time': len(content.split()) // 200,  # rough reading time in minutes
            'has_links': 'http' in content,
            'has_code': any(code_indicator in content for code_indicator in ['function', 'contract', 'API', 'endpoint'])
        }
    
    def _extract_topic_hints(self, text: str) -> List[str]:
        """Extract topic hints from a chunk of text for better categorization."""
        text_lower = text.lower()
        topics = []
        
        # Topic categories with keywords
        topic_keywords = {
            'technical': ['api', 'code', 'function', 'contract', 'implementation', 'protocol'],
            'business': ['partnership', 'funding', 'revenue', 'business', 'strategy', 'market'],
            'team': ['team', 'founder', 'ceo', 'developer', 'advisor', 'employee'],
            'tokenomics': ['token', 'supply', 'distribution', 'staking', 'rewards', 'economics'],
            'roadmap': ['roadmap', 'milestone', 'phase', 'timeline', 'future', 'planned'],
            'security': ['security', 'audit', 'safe', 'risk', 'vulnerability', 'protection']
        }
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                topics.append(topic)
        
        return topics[:3]  # Limit to top 3 topics
    
    def _get_relevant_content_for_question(self, question: str) -> str:
        """Intelligently select relevant content chunks based on user question."""
        question_lower = question.lower()
        relevant_sections = []
        
        # Start with DDQ content (always relevant)
        ddq_content = self._build_source_knowledgebase()
        if ddq_content:
            relevant_sections.append("# Core Project Information\n\n" + ddq_content)
        
        # Get enhanced scraped content
        scraped_content = st.session_state.get('notion_scraped_web_content', [])
        crawled_content = st.session_state.get('notion_crawled_web_content', [])
        
        # Combine all web content for analysis
        all_web_content = scraped_content + crawled_content
        
        # Find relevant chunks based on question keywords and topics
        relevant_chunks = self._find_relevant_chunks(question_lower, all_web_content)
        
        if relevant_chunks:
            web_section = "# Relevant Web Sources\n\n"
            for chunk_info in relevant_chunks:
                web_section += f"## {chunk_info['source_type']}: {chunk_info['url']}\n"
                web_section += f"**Relevance:** {chunk_info['relevance_reason']}\n"
                if chunk_info.get('metadata'):
                    metadata = chunk_info['metadata']
                    web_section += f"**Type:** {metadata.get('content_type', 'general')} | "
                    web_section += f"**Keywords:** {', '.join(metadata.get('keywords', []))}\n"
                web_section += f"\n{chunk_info['content']}\n\n---\n\n"
            
            relevant_sections.append(web_section)
        
        return "\n\n".join(relevant_sections) if relevant_sections else ""
    
    def _find_relevant_chunks(self, question_lower: str, web_content: List[Dict]) -> List[Dict]:
        """Find relevant chunks from web content based on question analysis."""
        relevant_chunks = []
        
        # Extract question keywords
        question_keywords = self._extract_question_keywords(question_lower)
        
        for content_item in web_content:
            url = content_item.get('url', 'Unknown')
            metadata = content_item.get('metadata', {})
            chunks = content_item.get('chunks', [])
            
            if not chunks:
                # Fallback to original content if no chunks
                original_content = content_item.get('original_content', content_item.get('content', ''))
                if self._is_content_relevant(question_keywords, original_content.lower(), metadata):
                    relevant_chunks.append({
                        'url': url,
                        'content': original_content[:2000],  # Limit size
                        'source_type': 'Scraped Content',
                        'relevance_reason': 'Contains relevant keywords',
                        'metadata': metadata
                    })
                continue
            
            # Check each chunk for relevance
            for chunk in chunks:
                chunk_text = chunk.get('text', '')
                chunk_topics = chunk.get('topic_hints', [])
                
                relevance_score, reason = self._calculate_chunk_relevance(
                    question_keywords, chunk_text.lower(), chunk_topics, metadata
                )
                
                if relevance_score > 0.3:  # Threshold for relevance
                    relevant_chunks.append({
                        'url': url,
                        'content': chunk_text,
                        'source_type': 'Scraped Content',
                        'relevance_reason': reason,
                        'relevance_score': relevance_score,
                        'chunk_id': chunk.get('chunk_id', 0),
                        'topics': chunk_topics,
                        'metadata': metadata
                    })
        
        # Sort by relevance score and limit results
        relevant_chunks.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return relevant_chunks[:5]  # Return top 5 most relevant chunks
    
    def _extract_question_keywords(self, question_lower: str) -> List[str]:
        """Extract meaningful keywords from user question."""
        # Remove common question words
        stop_words = {'what', 'how', 'when', 'where', 'why', 'who', 'is', 'are', 'the', 'a', 'an', 'and', 'or', 'but'}
        
        # Split question into words and filter
        words = [word.strip('?.,!') for word in question_lower.split()]
        keywords = [word for word in words if len(word) > 2 and word not in stop_words]
        
        return keywords[:10]  # Limit to top 10 keywords
    
    def _is_content_relevant(self, question_keywords: List[str], content_lower: str, metadata: Dict) -> bool:
        """Check if content is relevant based on keywords and metadata."""
        # Check direct keyword matches
        keyword_matches = sum(1 for keyword in question_keywords if keyword in content_lower)
        
        # Check metadata keywords
        meta_keywords = metadata.get('keywords', [])
        meta_matches = sum(1 for keyword in question_keywords 
                          if any(meta_keyword in keyword or keyword in meta_keyword 
                                for meta_keyword in meta_keywords))
        
        return (keyword_matches + meta_matches) >= 2  # At least 2 matches
    
    def _calculate_chunk_relevance(self, question_keywords: List[str], chunk_text: str, 
                                 chunk_topics: List[str], metadata: Dict) -> tuple[float, str]:
        """Calculate relevance score and provide reason for a content chunk."""
        score = 0.0
        reasons = []
        
        # Keyword matching (0-0.4 points)
        keyword_matches = sum(1 for keyword in question_keywords if keyword in chunk_text)
        if keyword_matches > 0:
            score += min(keyword_matches * 0.1, 0.4)
            reasons.append(f"{keyword_matches} keyword matches")
        
        # Topic relevance (0-0.3 points)
        relevant_topics = []
        for topic in chunk_topics:
            if any(keyword in topic for keyword in question_keywords):
                relevant_topics.append(topic)
        
        if relevant_topics:
            score += len(relevant_topics) * 0.1
            reasons.append(f"relevant topics: {', '.join(relevant_topics)}")
        
        # Metadata relevance (0-0.3 points)
        meta_keywords = metadata.get('keywords', [])
        meta_matches = sum(1 for keyword in question_keywords 
                          if any(meta_keyword in keyword or keyword in meta_keyword 
                                for meta_keyword in meta_keywords))
        if meta_matches > 0:
            score += min(meta_matches * 0.1, 0.3)
            reasons.append(f"metadata matches")
        
        reason = ", ".join(reasons) if reasons else "general relevance"
        return score, reason
    
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
        
        # Add DocSend deck content
        if additional_content.get('docsend_decks'):
            combined += "### 📊 DocSend Presentation Decks\n\n"
            for deck in additional_content['docsend_decks']:
                metadata = deck.get('metadata', {})
                slides_processed = metadata.get('processed_slides', 0)
                total_slides = metadata.get('total_slides', 0)
                
                combined += f"**DocSend Deck: {deck['url']}**\n"
                combined += f"Slides processed: {slides_processed}/{total_slides}\n"
                combined += f"Content extracted via OCR:\n\n{deck['content']}\n\n"
        
        return combined
    
    async def _run_enhanced_research(self, page_id, page_title, combined_content, model):
        """Run AI research on combined content using OpenRouterClient directly."""
        try:
            # Get our OpenRouter client
            client = st.session_state.get('notion_openrouter_client')
            if not client:
                raise RuntimeError("OpenRouter client not available")
            
            # Generate enhanced research report using our client directly
            research_prompt = f"""
Please analyze the following comprehensive research material and generate a detailed due diligence report.

# Research Material for {page_title}

{combined_content}

Please provide:
1. Executive Summary
2. Key Findings
3. Technology Analysis
4. Business Model Assessment
5. Risk Analysis
6. Market Analysis
7. Team Assessment
8. Financial Analysis
9. Competitive Landscape
10. Investment Recommendation

Format your response as a comprehensive markdown report with clear headings and bullet points.
Include specific data points and quotes from the source material where relevant.
"""
            
            # Generate the report using OpenRouterClient
            report_md = await client.generate_response(
                prompt=research_prompt,
                system_prompt="You are an expert investment analyst conducting due diligence research. Provide thorough, analytical insights based on the provided materials.",
                model_override=model
            )
            
            # Handle None response from API
            if not report_md:
                raise RuntimeError("AI model returned empty response - this may be due to SSL connectivity issues or API errors")
            
            # Save enhanced report to file
            from pathlib import Path
            reports_dir = Path("reports")
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_path = reports_dir / f"enhanced_report_{page_id}.md"
            report_path.write_text(report_md, encoding="utf-8")
            
            # Check if auto-publish to Notion is enabled
            auto_publish = st.session_state.get('notion_auto_publish_to_notion', False)
            notion_url = None
            
            if auto_publish:
                try:
                    # Import and use the Notion writer with username
                    from src.notion_writer import publish_report
                    
                    # Get username from session state
                    username = st.session_state.get('username', 'Unknown User')
                    
                    # Publish the report back to Notion as a child page with username attribution
                    notion_url = publish_report(page_id, report_path, username)
                    
                    self.show_success(f"✅ Report published to Notion: [AI Deep Research Report by {username}]({notion_url})")
                    
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
            
            # Build RAG context automatically (if available)
            await self._build_rag_context(report_id)
            
            return report_path
            
        except Exception as e:
            raise RuntimeError(f"Enhanced research failed: {str(e)}")
    
    def _get_sources_summary(self, uploaded_docs, web_urls, crawl_option, docsend_url=''):
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
        
        if docsend_url:
            sources.append("DocSend deck")
        
        return ", ".join(sources) if sources else "DDQ only"
    
    async def _manual_scoring_update(self) -> None:
        """Update scoring manually for selected pages."""
        try:
            selected_pages = st.session_state.get('notion_selected_pages', [])
            if not selected_pages:
                self.show_warning("⚠️ No pages selected for scoring")
                return
                
            page_lookup = st.session_state.get('notion_available_pages_lookup', {})
            self._start_operation(f"Scoring Update ({len(selected_pages)} pages)")
            
            successful_scoring = 0
            failed_scoring = 0
            
            for i, page_id in enumerate(selected_pages):
                page_info = page_lookup.get(page_id, {'title': f'Page {page_id[:8]}', 'id': page_id})
                progress = int((i + 1) / len(selected_pages) * 100)
                self._update_progress(progress, f"Scoring: {page_info['title']} ({i+1}/{len(selected_pages)})")
                
                try:
                    # Run actual project scoring
                    score_path = await run_project_scoring(page_id)
                    successful_scoring += 1
                    self.show_info(f"✅ Scored: {page_info['title']} → {score_path}")
                    
                    # Check if auto-publish to Notion is enabled
                    auto_publish_scoring = st.session_state.get('notion_auto_publish_scoring', False)
                    if auto_publish_scoring:
                        try:
                            # Load the scoring data and publish to Notion
                            import json
                            with open(score_path, 'r') as f:
                                score_data = json.load(f)
                            
                            await self._publish_scoring_to_notion(page_id, score_data)
                            self.show_success(f"📊 Scoring auto-published to Notion for {page_info['title']}")
                            
                        except Exception as publish_error:
                            self.show_warning(f"⚠️ Scoring completed but Notion auto-publish failed for {page_info['title']}: {str(publish_error)}")
                    
                except Exception as scoring_error:
                    failed_scoring += 1
                    error_msg = str(scoring_error)
                    
                    # Provide helpful guidance for common errors
                    if "not found in Notion" in error_msg or "file is missing" in error_msg:
                        self.show_warning(f"❌ {page_info['title']}: No research report found. Run Enhanced Research first.")
                    elif "run_deep_research" in error_msg:
                        self.show_warning(f"❌ {page_info['title']}: Research report required. Generate a report first.")
                    else:
                        self.show_warning(f"❌ Scoring failed for {page_info['title']}: {error_msg}")
                    continue
            
            # Add log entry
            self._add_automation_log(f"Scoring: {successful_scoring} success, {failed_scoring} failed out of {len(selected_pages)} pages")
            
            if successful_scoring > 0:
                self.show_success(f"✅ Scoring completed! {successful_scoring} success, {failed_scoring} failed")
            else:
                self.show_error(f"❌ All scoring attempts failed ({failed_scoring} total)")
                
            self._end_operation()
                
        except Exception as e:
            self._end_operation()
            self.show_error(f"Scoring update failed: {str(e)}")
    


    
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

    def _check_reports_exist(self, selected_pages: List[str]) -> bool:
        """Check if research reports exist for the selected pages."""
        has_reports, _ = self._check_reports_exist_detailed(selected_pages)
        return has_reports
    
    def _check_reports_exist_detailed(self, selected_pages: List[str]) -> tuple[bool, dict]:
        """Check if research reports exist for the selected pages with detailed status."""
        if not selected_pages:
            return False, {}
        
        from pathlib import Path
        reports_dir = Path("reports")
        
        if not reports_dir.exists():
            return False, {page_id: "Reports directory doesn't exist" for page_id in selected_pages}
        
        report_status = {}
        has_any_reports = False
        
        # Check each selected page
        for page_id in selected_pages:
            # Check for enhanced report file
            enhanced_report = reports_dir / f"enhanced_report_{page_id}.md"
            regular_report = reports_dir / f"report_{page_id}.md"
            
            if enhanced_report.exists():
                size = enhanced_report.stat().st_size
                report_status[page_id] = f"Found enhanced report ({size:,} bytes)"
                has_any_reports = True
            elif regular_report.exists():
                size = regular_report.stat().st_size
                report_status[page_id] = f"Found regular report ({size:,} bytes)"
                has_any_reports = True
            else:
                report_status[page_id] = "No report file found"
        
        return has_any_reports, report_status
    
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
            st.markdown("### 📊 **Generated Report**")
            
                    # Compact status display
        auto_publish = st.session_state.get('notion_auto_publish_to_notion', False)
        notion_url = st.session_state.get('notion_published_report_url')
        
        if auto_publish and notion_url:
            username = st.session_state.get('username', 'Unknown User')
            st.success(f"✅ **Published to Notion:** [AI Deep Research Report by {username}]({notion_url})")
        elif auto_publish:
            st.info("📁 Local save • Auto-publish enabled (URL not available)")
        else:
            st.info("📁 Local save only")
            
            # Actions row
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                # Download button
                st.download_button(
                    label="📥 Download Report",
                    data=st.session_state.notion_unified_report_content,
                    file_name=f"enhanced_notion_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    key="notion_download_report_btn"
                )
            with col2:
                report_chars = len(st.session_state.notion_unified_report_content)
                st.metric("Size", f"{report_chars:,} chars")
            with col3:
                rag_available = "✅" if st.session_state.get('notion_current_report_id_for_chat') in st.session_state.get('notion_rag_contexts', {}) else "❌"
                st.metric("Chat Ready", rag_available)
            
            # Report preview - expanded by default when results are shown
            with st.expander("# 📖 **View Full Report**", expanded=True):
                st.markdown(st.session_state.notion_unified_report_content)

    async def _render_scoring_results(self) -> None:
        """Render scoring results display."""
        # Check for scoring results
        selected_pages = st.session_state.get('notion_selected_pages', [])
        if not selected_pages:
            return
        
        from pathlib import Path
        import json
        reports_dir = Path("reports")
        
        scoring_results = []
        for page_id in selected_pages:
            score_file = reports_dir / f"score_{page_id}.json"
            if score_file.exists():
                try:
                    with open(score_file, 'r') as f:
                        score_data = json.load(f)
                    
                    # Get page info
                    available_pages = st.session_state.get('notion_available_pages', [])
                    page_info = next((p for p in available_pages if p['id'] == page_id), {'title': f'Page {page_id[:8]}'})
                    
                    scoring_results.append({
                        'page_id': page_id,
                        'page_title': page_info['title'], 
                        'score_data': score_data,
                        'file_path': score_file,
                        'file_size': score_file.stat().st_size
                    })
                except Exception as e:
                    st.error(f"Error loading score for {page_id}: {e}")
        
        if scoring_results:
            st.markdown("### 📊 **Project Scoring Results**")
            
            # Show current auto-publish status
            col1, col2 = st.columns([2, 1])
            with col1:
                auto_publish_enabled = st.session_state.get('notion_auto_publish_scoring', False)
                if auto_publish_enabled:
                    st.success("✅ Auto-publish to Notion: Enabled")
                else:
                    st.info("📁 Auto-publish to Notion: Disabled (configure in Workflow tab)")
            
            with col2:
                st.metric("Score Files", len(scoring_results))
            
            # Display each scoring result
            for result in scoring_results:
                with st.expander(f"# 🎯 **{result['page_title']} - Scoring Results**", expanded=False):
                    
                    # Key metrics in columns
                    col1, col2, col3, col4 = st.columns(4)
                    
                    score_data = result['score_data']
                    
                    with col1:
                        ido = score_data.get('IDO', 'N/A')
                        color = "🟢" if ido == "Yes" else "🔴" if ido == "No" else "⚪"
                        st.metric("IDO", f"{color} {ido}")
                    
                    with col2:
                        investment = score_data.get('Investment', 'N/A') 
                        color = "🟢" if investment == "Yes" else "🔴" if investment == "No" else "⚪"
                        st.metric("Investment", f"{color} {investment}")
                    
                    with col3:
                        advisory = score_data.get('Advisory', 'N/A')
                        color = "🟢" if advisory == "Yes" else "🔴" if advisory == "No" else "⚪"
                        st.metric("Advisory", f"{color} {advisory}")
                    
                    with col4:
                        conviction = score_data.get('Conviction', 'N/A')
                        st.metric("Conviction", conviction)
                    
                    # Show if this was a fallback/simplified scoring
                    expected_fields = ['IDO_Q1_TeamLegit', 'LA_Q1_Runway', 'MaxValuation_IDO']
                    has_detailed_fields = any(score_data.get(field) for field in expected_fields)
                    if not has_detailed_fields:
                        st.caption("🔄 Simplified scoring (detailed analysis failed)")
                        
                        # Debug: Show what fields are actually present
                        if st.checkbox("🔍 Show debug info", key=f"debug_score_{result['page_id']}"):
                            st.write("**Available fields in scoring data:**")
                            for key, value in score_data.items():
                                if value and value != 'N/A':
                                    st.write(f"✅ `{key}`: {str(value)[:100]}...")
                                else:
                                    st.write(f"❌ `{key}`: {value}")
                            
                            st.write(f"**Total fields:** {len(score_data)}")
                            st.write(f"**File size:** {result['file_size']} bytes")
                    
                    # Key insights
                    st.markdown("**📝 Key Insights:**")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**🐂 Bull Case:**")
                        st.info(score_data.get('BullCase', 'Not provided'))
                    
                    with col2:
                        st.markdown("**🐻 Bear Case:**")
                        st.warning(score_data.get('BearCase', 'Not provided'))
                    
                    # Rationales
                    if score_data.get('IDO_Rationale'):
                        st.markdown("**💡 IDO Rationale:**")
                        st.write(score_data['IDO_Rationale'])
                    
                    if score_data.get('Investment_Rationale'):
                        st.markdown("**💰 Investment Rationale:**")
                        st.write(score_data['Investment_Rationale'])
                    
                    # Valuations
                    col1, col2 = st.columns(2)
                    with col1:
                        if score_data.get('MaxValuation_IDO'):
                            st.markdown("**💎 Max IDO Valuation:**")
                            st.success(score_data['MaxValuation_IDO'])
                    
                    with col2:
                        if score_data.get('MaxValuation_Investment'):
                            st.markdown("**💼 Max Investment Valuation:**")
                            st.success(score_data['MaxValuation_Investment'])
                    
                    # Comments and scope
                    if score_data.get('ProposedScope'):
                        st.markdown("**🎯 Proposed Scope:**")
                        st.write(score_data['ProposedScope'])
                    
                    if score_data.get('Comments'):
                        st.markdown("**💬 Comments:**")
                        st.write(score_data['Comments'])
                    
                    # File info and download
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        # Download JSON
                        with open(result['file_path'], 'r') as f:
                            json_content = f.read()
                        
                        st.download_button(
                            label="📥 Download Scoring JSON",
                            data=json_content,
                            file_name=f"scoring_{result['page_id']}.json",
                            mime="application/json",
                            key=f"download_score_{result['page_id']}"
                        )
                    
                    with col2:
                        st.metric("File Size", f"{result['file_size']:,} B")
                    
                    with col3:
                        auto_publish_enabled = st.session_state.get('notion_auto_publish_scoring', False)
                        if auto_publish_enabled:
                            st.success("✅ Auto-published")
                        else:
                            if st.button(f"📤 Publish to Notion", key=f"publish_score_{result['page_id']}", type="primary"):
                                await self._publish_scoring_to_notion(result['page_id'], result['score_data'])

    async def _publish_scoring_to_notion(self, page_id: str, score_data: dict) -> None:
        """Publish scoring results to Notion as a child page."""
        try:
            from src.notion_writer import publish_report
            from pathlib import Path
            import tempfile
            
            # Create a markdown report from the scoring data
            username = st.session_state.get('username', 'Unknown User')
            
            markdown_content = f"""# Project Scoring Report

## Overall Recommendations

- **IDO**: {score_data.get('IDO', 'N/A')} 
- **Investment**: {score_data.get('Investment', 'N/A')}
- **Advisory**: {score_data.get('Advisory', 'N/A')}
- **Liquid Program**: {score_data.get('LiquidProgram', 'N/A')}

## Investment Analysis

### Bull Case
{score_data.get('BullCase', 'Not provided')}

### Bear Case  
{score_data.get('BearCase', 'Not provided')}

### Conviction
**{score_data.get('Conviction', 'N/A')}**
{score_data.get('Conviction_Rationale', '')}

## Valuation

### IDO Valuation
- **Max Valuation**: {score_data.get('MaxValuation_IDO', 'Not specified')}
- **Rationale**: {score_data.get('MaxValuation_IDO_Rationale', 'Not provided')}

### Investment Valuation
- **Max Valuation**: {score_data.get('MaxValuation_Investment', 'Not specified')}
- **Rationale**: {score_data.get('MaxValuation_Investment_Rationale', 'Not provided')}

## Recommendations

### Proposed Scope
{score_data.get('ProposedScope', 'Not specified')}

### Comments
{score_data.get('Comments', 'No additional comments')}

### Disclosures
{score_data.get('Disclosures', 'None specified')}

---
*Generated by AI Scoring System - {username}*
"""
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp_file:
                tmp_file.write(markdown_content)
                tmp_file_path = Path(tmp_file.name)
            
            try:
                # Use a custom approach since publish_report doesn't support custom titles
                # We'll create our own Notion page for scoring
                notion_url = await self._create_scoring_notion_page(page_id, markdown_content, username)
                
                st.success(f"✅ Scoring published to Notion: [Project Scoring by {username}]({notion_url})")
                
            finally:
                # Clean up temp file
                tmp_file_path.unlink(missing_ok=True)
                
        except Exception as e:
            st.error(f"Failed to publish scoring to Notion: {str(e)}")

    async def _create_scoring_notion_page(self, page_id: str, markdown_content: str, username: str) -> str:
        """Create a custom Notion page for scoring results."""
        import os
        import httpx
        from notion_client import Client as NotionClient
        from notion_client.errors import RequestTimeoutError, APIResponseError
        from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential
        from typing import cast
        
        def _is_retryable(exc: Exception) -> bool:
            if isinstance(exc, (RequestTimeoutError, httpx.TimeoutException)):
                return True
            if isinstance(exc, APIResponseError):
                if exc.code in {"internal_server_error", "service_unavailable", "rate_limited"}:
                    return True
                status = getattr(exc, "status", 0) or 0
                return isinstance(status, int) and (status == 429 or status // 100 == 5)
            return False

        def _tenacity() -> Retrying:
            return Retrying(
                wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
                stop=stop_after_attempt(3),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            )
        
        # Initialize Notion client
        token = os.getenv("NOTION_TOKEN")
        if not token:
            raise RuntimeError("Environment variable NOTION_TOKEN is required.")
        
        timeout_cfg = httpx.Timeout(180.0, connect=10.0)
        client = NotionClient(auth=token, client=httpx.Client(timeout=timeout_cfg))
        
        # Add current date to the title in DD Month YYYY format
        from datetime import datetime
        current_date = datetime.now().strftime("%d %B %Y")
        page_title = f"Project Scoring by {username} ({current_date})"
        
        # Convert markdown to simple blocks (paragraph blocks)
        lines = markdown_content.split('\n')
        blocks = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('# '):
                blocks.append({
                    "type": "heading_1",
                    "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]},
                })
            elif line.startswith('## '):
                blocks.append({
                    "type": "heading_2", 
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]},
                })
            elif line.startswith('### '):
                blocks.append({
                    "type": "heading_3",
                    "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]},
                })
            elif line.startswith('- '):
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]},
                })
            else:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]},
                })
        
        # Create the page
        first_batch = blocks[:100]  # Notion API limit
        
        for attempt in _tenacity():
            with attempt:
                new_page = client.pages.create(
                    parent={"type": "page_id", "page_id": page_id},
                    properties={
                        "title": {
                            "title": [
                                {"type": "text", "text": {"content": page_title}}
                            ]
                        }
                    },
                    icon={"emoji": "📊"},
                    children=first_batch,
                )
        
        report_page_id = cast(str, new_page["id"])
        report_url = cast(str, new_page["url"])
        
        # Append remaining blocks if any
        remaining_blocks = blocks[100:]
        if remaining_blocks:
            # Split into chunks of 100
            for i in range(0, len(remaining_blocks), 100):
                batch = remaining_blocks[i:i+100]
                for attempt in _tenacity():
                    with attempt:
                        client.blocks.children.append(block_id=report_page_id, children=batch)
        
        return report_url

    async def _render_admin_panel(self) -> None:
        """Render admin panel if user is admin."""
        st.markdown("---")
        st.subheader("🔧 Admin Panel")
        
        # Environment Status
        import os
        required_vars = ["NOTION_TOKEN", "NOTION_DB_ID", "OPENROUTER_API_KEY"]
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            st.error(f"❌ Missing environment variables: {', '.join(missing)}")
        else:
            st.success("✅ Environment configured correctly")
        
        # Monitoring Section
        st.markdown("### 📡 **Notion Database Monitoring**")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            is_active = st.session_state.get('notion_polling_active', False)
            status = "🟢 ACTIVE" if is_active else "⚪ INACTIVE"
            st.metric("Auto-Monitoring", status)
        
        with col2:
            last_poll = st.session_state.get('notion_last_poll_time')
            if last_poll and isinstance(last_poll, datetime):
                time_str = last_poll.strftime("%H:%M")
            else:
                time_str = "Never"
            st.metric("Last Poll", time_str)
        
        # Monitoring Control buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("▶️ Start Auto-Monitor", key="admin_start_monitoring_btn"):
                await self._start_notion_monitoring()
        with col2:
            if st.button("⏹️ Stop Auto-Monitor", key="admin_stop_monitoring_btn"):  
                await self._stop_notion_monitoring()
        with col3:
            if st.button("🔍 Manual Poll", key="admin_manual_poll_btn"):
                await self._manual_poll_database()
        
        # Poll results
        if st.session_state.get('notion_last_poll_results'):
            results = st.session_state.notion_last_poll_results
            pages_found = results.get('total_entries', 0)
            if pages_found > 0:
                st.caption(f"💡 Last poll found {pages_found} pages with completed DDQs")
            else:
                st.caption("💡 Last poll found no new completed DDQs")
        
        st.markdown("---")
        
        # System Management
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
            with st.expander("# 💬 **Chat with AI about Enhanced Report**", expanded=st.session_state.get('notion_chat_ui_expanded', False)):
                report_id = st.session_state.notion_current_report_id_for_chat
                
                # Chat uses enhanced content analysis with chunked storage
                st.success("💬 **Enhanced Chat Ready** - Ask questions about DDQ content, documents, and scraped web sources!")
                
                # Chat input (always available)
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
                
                # RAG building removed - disabled on macOS and confusing to users
                # Chat now uses improved chunked storage for scraped content

    async def _process_chat_question(self, question: str, report_id: str) -> None:
        """Process a chat question using RAG context or direct AI analysis."""
        try:
            with st.spinner("🤔 AI is thinking..."):
                # Initialize chat sessions if not exists and log session creation
                if 'notion_chat_sessions_store' not in st.session_state:
                    st.session_state.notion_chat_sessions_store = {}
                
                if report_id not in st.session_state.notion_chat_sessions_store:
                    st.session_state.notion_chat_sessions_store[report_id] = []
                    
                    # Log session creation for new chat sessions
                    username = st.session_state.get('username', 'UNKNOWN')
                    if username != 'UNKNOWN':
                        try:
                            session_id = f"streamlit_notion_{report_id}_{username}"
                            user_history_service.log_session_created(username, session_id, report_id)
                        except Exception as e:
                            self.logger.warning(f"Error logging session creation: {e}")
                
                rag_context = st.session_state.get('notion_rag_contexts', {}).get(report_id)
                client = st.session_state.get('notion_openrouter_client')
                
                if not client:
                    self.show_error("OpenRouter client not available")
                    return
                
                if rag_context:
                    # RAG-based response (preferred when available)
                    try:
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
                        
                        prompt = f"""Based on the following context from the research report, please answer the user's question.
                        
Context:
{context}

Question: {question}

Please provide a helpful and accurate answer based on the context provided."""
                        
                        system_prompt = "You are a helpful research assistant. Answer questions based on the provided context."
                        response_method = "RAG-enhanced"
                        
                    except Exception as rag_error:
                        # RAG failed, fall back to direct analysis
                        st.warning(f"RAG processing failed: {str(rag_error)}. Using direct analysis.")
                        rag_context = None
                
                if not rag_context:
                    # Enhanced content analysis using intelligent chunk selection
                    relevant_content = self._get_relevant_content_for_question(question)
                    
                    if relevant_content:
                        prompt = f"""Based on the following relevant source materials (intelligently selected from DDQ content, documents, and enhanced scraped web sources), please answer the user's question.

Relevant Source Materials:
{relevant_content}

Question: {question}

Please provide a helpful and accurate answer based on the relevant source materials provided. Reference specific sections or sources when possible."""
                        
                        system_prompt = "You are a helpful research assistant. Analyze the relevant source materials and provide specific, accurate answers with source references."
                        response_method = "Enhanced content analysis"
                    else:
                        # Ultimate fallback - general response
                        prompt = f"""The user is asking about a research project: "{question}"

Please provide a helpful response acknowledging that you don't have access to the specific project data, but offer general guidance about the topic if possible."""
                        
                        system_prompt = "You are a helpful research assistant. Provide general guidance when specific project data is not available."
                        response_method = "General guidance"
                
                # Always use Qwen 3 30B for chat regardless of user's model selection
                model_to_use = "qwen/qwen3-30b-a3b:free"
                response = await client.generate_response(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model_override=model_to_use
                )
                
                if response:
                    # Store in chat history
                    chat_history = st.session_state.get('notion_chat_sessions_store', {}).get(report_id, [])
                    chat_history.append({
                        'question': question,
                        'answer': response,
                        'method': response_method,
                        'timestamp': pd.Timestamp.now().strftime('%H:%M:%S')
                    })
                    
                    if 'notion_chat_sessions_store' not in st.session_state:
                        st.session_state.notion_chat_sessions_store = {}
                    st.session_state.notion_chat_sessions_store[report_id] = chat_history
                    
                    # Log to user history service
                    username = st.session_state.get('username', 'UNKNOWN')
                    if username != 'UNKNOWN':
                        try:
                            session_id = f"streamlit_notion_{report_id}_{username}"
                            user_history_service.log_chat_message(
                                username=username,
                                session_id=session_id,
                                report_id=report_id,
                                query=question,
                                response=response
                            )
                        except Exception as e:
                            self.logger.warning(f"Error logging chat message: {e}")
                    
                    self.show_success(f"✅ Answer generated using {response_method}!")
                    st.rerun()
                else:
                    self.show_error("AI returned empty response")
                    
        except Exception as e:
            self.show_error(f"Chat processing failed: {str(e)}")
    
    def _display_chat_history(self, report_id: str) -> None:
        """Display chat history for the report."""
        chat_history = st.session_state.get('notion_chat_sessions_store', {}).get(report_id, [])
        
        if chat_history:
            st.markdown("### 📝 **Chat History**")
            for i, chat in enumerate(reversed(chat_history[-5:])):  # Show last 5 chats
                with st.container():
                    # Show method used for the response
                    method = chat.get('method', 'Unknown')
                    method_icon = ("🧠" if method == "RAG-enhanced" else 
                                 "🎯" if method == "Enhanced content analysis" else 
                                 "📚" if method == "Source analysis" else 
                                 "🤖" if method == "Direct analysis" else "💭")
                    
                    st.markdown(f"**🙋 Question ({chat['timestamp']}):**")
                    st.markdown(f"> {chat['question']}")
                    st.markdown(f"**{method_icon} Answer ({method}):**")
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
            # RAG disabled - silently set to None without confusing user messages
            st.session_state.notion_rag_contexts[report_id] = None 
    
    def _build_source_knowledgebase(self) -> str:
        """Build comprehensive knowledgebase from DDQ content and additional sources."""
        source_sections = []
        
        # Get selected pages DDQ content (Step 2)
        selected_pages = st.session_state.get('notion_selected_pages', [])
        available_pages = st.session_state.get('notion_available_pages', [])
        page_lookup = {p['id']: p for p in available_pages}
        
        for page_id in selected_pages:
            page_info = page_lookup.get(page_id, {'title': f'Page {page_id[:8]}', 'id': page_id})
            
            try:
                # Get DDQ content components
                from src.notion_research import _fetch_ddq_markdown, _fetch_calls_text, _fetch_freeform_text
                
                ddq_content = _fetch_ddq_markdown(page_id) or "DDQ content not available."
                calls_content = _fetch_calls_text(page_id) or "Call notes not available."
                freeform_content = _fetch_freeform_text(page_id) or "Freeform content not available."
                
                # Add to source sections
                page_section = f"""## 📋 Notion Project: {page_info['title']}

### Due Diligence Questionnaire
{ddq_content}

### Call Notes
{calls_content}

### Additional Project Information
{freeform_content}

---"""
                source_sections.append(page_section)
                
            except Exception as e:
                # If DDQ fetch fails, note it but continue
                error_section = f"""## 📋 Notion Project: {page_info['title']}

⚠️ Error fetching DDQ content: {str(e)}

---"""
                source_sections.append(error_section)
        
        # Get additional sources from Step 3
        additional_sources = self._build_additional_sources_content()
        if additional_sources:
            source_sections.append(additional_sources)
        
        return "\n\n".join(source_sections) if source_sections else ""
    
    def _build_additional_sources_content(self) -> str:
        """Build content from additional sources (Step 3) using enhanced chunked storage."""
        additional_sections = []
        
        # Uploaded documents
        processed_docs = st.session_state.get('notion_processed_documents_content', [])
        if processed_docs:
            doc_section = "## 📄 Additional Documents\n\n"
            for doc in processed_docs:
                doc_section += f"### Document: {doc['name']}\n{doc['text']}\n\n"
            additional_sections.append(doc_section)
        
        # Web content - use enhanced chunked storage
        scraped_web_content = st.session_state.get('notion_scraped_web_content', [])
        if scraped_web_content:
            web_section = "## 🌐 Enhanced Scraped Web Content\n\n"
            for page in scraped_web_content:
                metadata = page.get('metadata', {})
                web_section += f"### URL: {page['url']}\n"
                web_section += f"**Domain:** {metadata.get('domain', 'Unknown')} | "
                web_section += f"**Type:** {metadata.get('content_type', 'general')} | "
                web_section += f"**Keywords:** {', '.join(metadata.get('keywords', []))}\n\n"
                
                # Use chunks for better organization
                chunks = page.get('chunks', [])
                if chunks:
                    for chunk in chunks:
                        topics = chunk.get('topic_hints', [])
                        topic_info = f" ({', '.join(topics)})" if topics else ""
                        web_section += f"**Content Section {chunk['chunk_id'] + 1}{topic_info}:**\n{chunk['text']}\n\n"
                else:
                    # Fallback to original content if no chunks
                    web_section += f"{page.get('original_content', page.get('content', ''))}\n\n"
            additional_sections.append(web_section)
        
        # Crawled content - use enhanced chunked storage
        crawled_web_content = st.session_state.get('notion_crawled_web_content', [])
        if crawled_web_content:
            crawl_section = "## 🕷️ Enhanced Crawled Web Content\n\n"
            for page in crawled_web_content:
                metadata = page.get('metadata', {})
                crawl_section += f"### URL: {page['url']}\n"
                crawl_section += f"**Domain:** {metadata.get('domain', 'Unknown')} | "
                crawl_section += f"**Type:** {metadata.get('content_type', 'general')} | "
                crawl_section += f"**Keywords:** {', '.join(metadata.get('keywords', []))}\n\n"
                
                # Use chunks for better organization
                chunks = page.get('chunks', [])
                if chunks:
                    for chunk in chunks:
                        topics = chunk.get('topic_hints', [])
                        topic_info = f" ({', '.join(topics)})" if topics else ""
                        crawl_section += f"**Content Section {chunk['chunk_id'] + 1}{topic_info}:**\n{chunk['text']}\n\n"
                else:
                    # Fallback to original content if no chunks
                    crawl_section += f"{page.get('original_content', page.get('content', ''))}\n\n"
            additional_sections.append(crawl_section)
        
        # DocSend deck content
        docsend_content = st.session_state.get('notion_docsend_content', '')
        docsend_metadata = st.session_state.get('notion_docsend_metadata', {})
        if docsend_content:
            docsend_section = "## 📊 DocSend Presentation Deck (OCR Extracted)\n\n"
            docsend_section += f"**URL:** {docsend_metadata.get('url', 'Unknown')}\n"
            docsend_section += f"**Slides processed:** {docsend_metadata.get('processed_slides', 0)}/{docsend_metadata.get('total_slides', 0)}\n"
            docsend_section += f"**Total characters:** {docsend_metadata.get('total_characters', 0):,}\n"
            docsend_section += f"**Processing time:** {docsend_metadata.get('processing_time', 0):.1f} seconds\n\n"
            docsend_section += f"**Full OCR Content:**\n{docsend_content}\n\n"
            additional_sections.append(docsend_section)
        
        # If no scraped content available, show configuration info for transparency
        web_urls = st.session_state.get('notion_web_urls', [])
        selected_sitemap_urls = st.session_state.get('notion_selected_sitemap_urls', set())
        crawl_option = st.session_state.get('notion_crawl_option', 'None')
        docsend_url = st.session_state.get('notion_docsend_url', '')
        
        if not scraped_web_content and not crawled_web_content and not docsend_content:
            config_info = []
            if web_urls:
                config_info.append(f"🌐 {len(web_urls)} Web URLs configured")
            if selected_sitemap_urls:
                config_info.append(f"🗺️ {len(selected_sitemap_urls)} Sitemap URLs selected")
            if crawl_option != 'None':
                config_info.append(f"🕷️ Website crawling: {crawl_option}")
            if docsend_url:
                config_info.append(f"📊 DocSend deck: {docsend_url}")
            
            if config_info:
                config_section = "## 🔧 Additional Sources Configuration\n\n"
                config_section += "The following additional sources were configured for research:\n\n"
                for info in config_info:
                    config_section += f"- {info}\n"
                config_section += "\n*Note: Web content and DocSend content will be available after running Enhanced Research.*\n\n"
                additional_sections.append(config_section)
        
        if additional_sections:
            return f"# 📚 Additional Research Sources\n\n" + "\n".join(additional_sections)
        else:
            return ""