"""
Interactive Research Page for AI Research Agent.
Handles document upload, web scraping, and AI report generation.
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
import io
import re
from urllib.parse import urlparse, urljoin
from datetime import datetime
import time

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from docx import Document
except ImportError:
    Document = None

from src.pages.base_page import BasePage
from src.openrouter import OpenRouterClient
from src.firecrawl_client import FirecrawlClient
from src.config import OPENROUTER_PRIMARY_MODEL, AI_MODEL_OPTIONS
from src.core.scanner_utils import discover_sitemap_urls
from src.core.rag_utils import (
    get_embedding_model,
    split_text_into_chunks,
    build_faiss_index,
    search_faiss_index,
    DEFAULT_EMBEDDING_MODEL,
    TOP_K_RESULTS
)
from src.models.chat_models import ChatSession, ChatHistoryItem, UserHistoryEntry
from src.services.user_history_service import user_history_service
from src.audit_logger import (
    get_audit_logger, 
    log_ai_interaction, 
    log_document_processing, 
    log_web_scraping, 
    log_docsend_processing, 
    log_user_action
)

class InteractiveResearchPage(BasePage):
    """Interactive Research page with document processing and AI analysis."""
    
    def __init__(self):
        super().__init__("interactive_research", "Interactive Research")
        
        # Use standardized model options from config
        self.model_options = AI_MODEL_OPTIONS
        self.model_display_names = list(AI_MODEL_OPTIONS.values())
    
    async def render(self) -> None:
        """Render the interactive research page."""
        if not self.check_authentication():
            self.show_auth_required_message()
            return
        
        # Log page access
        self._log_page_access()
        
        # Initialize session state
        self._init_session_state()
        
        # Initialize clients
        self._init_clients()
        
        # Render sidebar with history
        self._render_sidebar_history()
        
        # Show page content
        self.show_page_header("Unified Research Interface")
        
        # Model selection
        await self._render_model_selection()
        
        # Research query input
        await self._render_research_query()
        
        # Document upload
        await self._render_document_upload()
        
        # URL input
        await self._render_url_input()
        
        # Crawl & scrape
        await self._render_crawl_section()
        
        # DocSend decks
        await self._render_docsend_section()
        
        # Report generation
        await self._render_report_generation()
        
        # Display generated report
        await self._render_report_display()
        
        # Debug: Show current role for troubleshooting
        current_role = st.session_state.get("role", "NOT_SET")
        current_user = st.session_state.get("username", "NOT_SET")
        
        # Always show debug info for now
        with st.expander("🔧 Debug Info", expanded=False):
            st.write(f"**Current User:** {current_user}")
            st.write(f"**Current Role:** {current_role}")
            st.write(f"**Session State Keys:** {list(st.session_state.keys())}")
            
            # Show authentication status
            auth_status = "✅ Authenticated" if st.session_state.get("authenticated") else "❌ Not Authenticated"
            st.write(f"**Auth Status:** {auth_status}")
        
        # Admin panel (if admin)
        if st.session_state.get("role") == "admin":
            await self._render_admin_panel()
        
        # Chat interface
        await self._render_chat_interface()
    
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
                                key=f"session_{session['session_id']}",
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
                if st.button("🔄 Refresh History", use_container_width=True):
                    st.rerun()
                
                # Clear old history button
                if st.button("🧹 Clear Old History", use_container_width=True):
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
            st.session_state.current_report_id_for_chat = session['report_id']
            st.session_state.report_generated_for_chat = True
            
            # Expand chat interface
            st.session_state.chat_ui_expanded = True
            
            # Log session resume
            user_history_service.add_activity(
                UserHistoryEntry(
                    username=session['username'],
                    activity_type='session_resumed',
                    session_id=session['session_id'],
                    report_id=session['report_id'],
                    details={'action': 'resumed_from_sidebar'}
                )
            )
            
            st.success(f"📂 Resumed session for {session['report_id']}")
            st.rerun()
            
        except Exception as e:
            st.error(f"Error resuming session: {str(e)}")
    
    def _log_page_access(self) -> None:
        """Log user access to the Interactive Research page."""
        log_user_action(
            user=st.session_state.get('username', 'UNKNOWN'),
            role=st.session_state.get('role', 'N/A'),
            action="PAGE_ACCESS",
            page="Interactive Research",
            details="User accessed Interactive Research page"
        )
    
    def _init_session_state(self) -> None:
        """Initialize required session state keys."""
        required_keys = {
            'processed_documents_content': [],
            'last_uploaded_file_details': [],
            'unified_report_content': "",
            'scraped_web_content': [],
            'crawled_web_content': [],
            'discovered_sitemap_urls': [],
            'sitemap_scan_in_progress': False,
            'sitemap_scan_error': None,
            'sitemap_scan_completed': False,
            'selected_sitemap_urls': set(),
            'chat_sessions_store': {},
            'current_chat_session_id': None,
            'rag_contexts': {},
            'report_generated_for_chat': False,
            'current_report_id_for_chat': None,
            'chat_ui_expanded': False,
            'ai_is_thinking': False,
            'last_user_prompt_for_processing': None,
            'docsend_content': '',
            'docsend_metadata': {},
        }
        self.init_session_state(required_keys)
    
    def _init_clients(self) -> None:
        """Initialize API clients."""
        if "openrouter_client" not in st.session_state:
            openrouter_client = OpenRouterClient()
            firecrawl_client = FirecrawlClient(redis_url=None)  # No Redis for now
            st.session_state.openrouter_client = openrouter_client
            st.session_state.firecrawl_client = firecrawl_client
    
    async def _render_model_selection(self) -> None:
        """Render the model selection section."""
        st.subheader("Model Selection")
        
        try:
            default_model_identifier = OPENROUTER_PRIMARY_MODEL
            
            # Find the default model description
            default_display_name = self.model_options.get(default_model_identifier, "")
            
            if default_display_name:
                default_index = self.model_display_names.index(default_display_name)
            else:
                st.warning(f"Default model '{default_model_identifier}' not found. Using first option.")
                default_index = 0
                
        except ValueError:
            default_index = 0
            st.warning(f"Could not determine default index. Using first option.")
        
        selected_model_display_name = st.selectbox(
            "Choose the AI model for report generation:",
            options=self.model_display_names,
            index=default_index,
            key="model_selector",
            help="Select the AI model to use for generating reports."
        )
        
        # Find the model identifier from the display name
        selected_model_identifier = None
        for identifier, description in self.model_options.items():
            if description == selected_model_display_name:
                selected_model_identifier = identifier
                break
        
        # Log model selection if changed
        if st.session_state.get('previous_selected_model') != selected_model_identifier:
            log_user_action(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="MODEL_SELECTED",
                page="Interactive Research",
                details=f"Selected AI model: {selected_model_display_name}",
                additional_context={"model_identifier": selected_model_identifier}
            )
            st.session_state.previous_selected_model = selected_model_identifier
        
        st.session_state.selected_model = selected_model_identifier
        st.markdown("---")
    
    async def _render_research_query(self) -> None:
        """Render the research query input section."""
        st.subheader("1. Define Your Research Focus (Optional)")
        research_query = st.text_area(
            "Enter your research query or specific questions:",
            height=100,
            key="research_query_input",
            help="Clearly state what you want the AI to investigate or analyze."
        )
        
        # Log research query input if provided and changed
        if research_query and research_query != st.session_state.get('previous_research_query', ''):
            log_user_action(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="RESEARCH_QUERY_INPUT",
                page="Interactive Research",
                details=f"Research query entered: {research_query[:100]}{'...' if len(research_query) > 100 else ''}",
                additional_context={
                    "query_length": len(research_query),
                    "query_words": len(research_query.split())
                }
            )
            st.session_state.previous_research_query = research_query
        
        return research_query
    
    async def _render_document_upload(self) -> None:
        """Render the document upload section."""
        st.subheader("2. Upload Relevant Documents (Optional)")
        
        uploaded_files = st.file_uploader(
            "Upload documents (PDF, DOCX, TXT, MD)",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
            key="document_uploader",
            help="Upload relevant documents for analysis."
        )
        
        if uploaded_files:
            await self._process_uploaded_files(uploaded_files)
    
    async def _process_uploaded_files(self, uploaded_files) -> None:
        """Process uploaded files and extract text content."""
        current_file_details = [(f.name, f.size) for f in uploaded_files]
        files_have_changed = (current_file_details != st.session_state.get("last_uploaded_file_details", []))
        
        if not files_have_changed:
            return
        
        st.session_state.last_uploaded_file_details = current_file_details
        st.session_state.processed_documents_content = []
        processed_content = []
        
        with st.status(f"Processing {len(uploaded_files)} file(s)...", expanded=True) as status:
            for i, file_data in enumerate(uploaded_files):
                st.write(f"Processing: {file_data.name} ({i+1}/{len(uploaded_files)})")
                
                try:
                    content = await self._extract_file_content(file_data)
                    if content:
                        processed_content.append({"name": file_data.name, "text": content})
                        self.show_success(f"Successfully processed: {file_data.name}")
                        
                        # Log successful document processing
                        log_document_processing(
                            user=st.session_state.get('username', 'UNKNOWN'),
                            role=st.session_state.get('role', 'N/A'),
                            filename=file_data.name,
                            file_type=file_data.type or 'unknown',
                            file_size=file_data.size,
                            success=True,
                            extracted_length=len(content)
                        )
                    else:
                        self.show_error(f"Failed to extract content from: {file_data.name}")
                        
                        # Log failed document processing
                        log_document_processing(
                            user=st.session_state.get('username', 'UNKNOWN'),
                            role=st.session_state.get('role', 'N/A'),
                            filename=file_data.name,
                            file_type=file_data.type or 'unknown',
                            file_size=file_data.size,
                            success=False,
                            extracted_length=0
                        )
                        
                except Exception as e:
                    self.show_error(f"Error processing {file_data.name}: {str(e)}")
                    
                    # Log exception in document processing
                    log_document_processing(
                        user=st.session_state.get('username', 'UNKNOWN'),
                        role=st.session_state.get('role', 'N/A'),
                        filename=file_data.name,
                        file_type=getattr(file_data, 'type', 'unknown'),
                        file_size=getattr(file_data, 'size', 0),
                        success=False,
                        extracted_length=0
                    )
            
            st.session_state.processed_documents_content = processed_content
            status.update(
                label=f"Processed {len(processed_content)}/{len(uploaded_files)} files successfully",
                state="complete",
                expanded=False
            )
        
        # Display processed documents summary
        if processed_content:
            st.markdown("---")
            st.subheader(f"Processed Documents ({len(processed_content)} ready)")
            for doc in processed_content:
                with st.expander(f"{doc['name']} ({len(doc['text'])} chars)"):
                    preview_text = doc['text'][:250] + "..." if len(doc['text']) > 250 else doc['text']
                    st.text(preview_text)
            st.markdown("---")
    
    async def _extract_file_content(self, file_data) -> str:
        """Extract text content from uploaded file."""
        file_bytes = file_data.getvalue()
        file_extension = file_data.name.split('.')[-1].lower()
        
        if file_extension == "pdf":
            return self._extract_pdf_content(file_bytes)
        elif file_extension == "docx":
            return self._extract_docx_content(file_bytes)
        elif file_extension in ["txt", "md"]:
            return self._extract_text_content(file_bytes)
        else:
            st.warning(f"Unsupported file type: {file_extension}")
            return ""
    
    def _extract_pdf_content(self, file_bytes: bytes) -> str:
        """Extract text from PDF file."""
        if not fitz:
            st.error("PyMuPDF not installed. Cannot process PDF files.")
            return ""
        
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text += page.get_text()
            doc.close()
            return text
        except Exception as e:
            st.error(f"Error processing PDF: {e}")
            return ""
    
    def _extract_docx_content(self, file_bytes: bytes) -> str:
        """Extract text from DOCX file."""
        if not Document:
            st.error("python-docx not installed. Cannot process DOCX files.")
            return ""
        
        try:
            doc = Document(io.BytesIO(file_bytes))
            text = "\n".join([para.text for para in doc.paragraphs])
            return text
        except Exception as e:
            st.error(f"Error processing DOCX: {e}")
            return ""
    
    def _extract_text_content(self, file_bytes: bytes) -> str:
        """Extract text from TXT/MD file."""
        try:
            return file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return file_bytes.decode('latin-1')
            except Exception as e:
                st.error(f"Error decoding text file: {e}")
                return ""
    
    async def _render_url_input(self) -> None:
        """Render the URL input section."""
        st.subheader("3. Provide Specific Web URLs (Optional)")
        
        urls_text_area = st.text_area(
            "Enter URLs, one per line:",
            height=150,
            key="urls_input",
            placeholder="https://example.com/page1\nhttps://example.com/page2"
        )
        
        if urls_text_area:
            submitted_urls = [url.strip() for url in urls_text_area.split('\n') if url.strip()]
            
            # Log URL input if provided and changed
            previous_urls = st.session_state.get('previous_urls_input', '')
            if urls_text_area != previous_urls:
                log_user_action(
                    user=st.session_state.get('username', 'UNKNOWN'),
                    role=st.session_state.get('role', 'N/A'),
                    action="URLS_INPUT",
                    page="Interactive Research",
                    details=f"URLs entered: {len(submitted_urls)} URLs",
                    additional_context={
                        "urls": submitted_urls,
                        "url_count": len(submitted_urls),
                        "total_text_length": len(urls_text_area)
                    }
                )
                st.session_state.previous_urls_input = urls_text_area
            
            return submitted_urls
        return []
    
    async def _render_crawl_section(self) -> None:
        """Render the crawl and scrape section."""
        st.subheader("4. Crawl & Scrape Site (Optional)")
        
        st.markdown("""
        **Option A: Scan Site Sitemap** - Get list of all pages
        **Option B: Crawl from URL** - Follow links automatically
        """)
        
        # Sitemap scanning
        await self._render_sitemap_scan()
        
        # Direct crawling
        await self._render_direct_crawl()
    
    async def _render_sitemap_scan(self) -> None:
        """Render sitemap scanning functionality."""
        st.markdown("**Option A: Scan Site for URLs from Sitemap**")
        
        site_url = st.text_input(
            "URL to scan for sitemap:",
            key="sitemap_scan_url",
            placeholder="https://example.com"
        )
        
        if st.button("Scan Site for URLs", key="scan_sitemap_btn"):
            if site_url:
                await self._scan_sitemap(site_url)
            else:
                self.show_warning("Please enter a URL to scan.")
        
        # Display scan results
        await self._render_sitemap_results()
    
    async def _scan_sitemap(self, site_url: str) -> None:
        """Scan site for sitemap URLs."""
        st.session_state.sitemap_scan_in_progress = True
        st.session_state.discovered_sitemap_urls = []
        st.session_state.sitemap_scan_error = None
        st.session_state.sitemap_scan_completed = False
        
        # Log sitemap scan initiation
        log_user_action(
            user=st.session_state.get('username', 'UNKNOWN'),
            role=st.session_state.get('role', 'N/A'),
            action="SITEMAP_SCAN_INITIATED",
            page="Interactive Research",
            details=f"Sitemap scan started for: {site_url}",
            additional_context={"target_url": site_url}
        )
        
        try:
            with st.spinner(f"Scanning {site_url} for sitemap URLs..."):
                discovered_urls = await discover_sitemap_urls(site_url)
            
            st.session_state.discovered_sitemap_urls = discovered_urls
            st.session_state.sitemap_scan_completed = True
            
            # Log sitemap scan results
            log_user_action(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="SITEMAP_SCAN_COMPLETED",
                page="Interactive Research",
                details=f"Sitemap scan completed: {len(discovered_urls)} URLs found",
                additional_context={
                    "target_url": site_url,
                    "urls_found": len(discovered_urls),
                    "discovered_urls": discovered_urls[:10] if discovered_urls else []  # Log first 10 URLs
                }
            )
            
            if discovered_urls:
                self.show_success(f"Found {len(discovered_urls)} URLs!")
            else:
                self.show_info("No URLs found in sitemap.")
                
        except Exception as e:
            error_msg = f"Sitemap scan failed: {str(e)}"
            st.session_state.sitemap_scan_error = error_msg
            
            # Log sitemap scan failure
            log_user_action(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="SITEMAP_SCAN_FAILED",
                page="Interactive Research",
                details=f"Sitemap scan failed for {site_url}: {error_msg}",
                additional_context={"target_url": site_url, "error": str(e)}
            )
            
            self.show_error(error_msg)
            st.session_state.sitemap_scan_completed = True
        finally:
            st.session_state.sitemap_scan_in_progress = False
            st.rerun()
    
    async def _render_sitemap_results(self) -> None:
        """Render sitemap scan results and URL selection."""
        if st.session_state.sitemap_scan_completed and st.session_state.discovered_sitemap_urls:
            st.subheader("Select URLs for Scraping:")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Select All", key="select_all_urls"):
                    st.session_state.selected_sitemap_urls = set(st.session_state.discovered_sitemap_urls)
                    st.rerun()
            with col2:
                if st.button("Deselect All", key="deselect_all_urls"):
                    st.session_state.selected_sitemap_urls = set()
                    st.rerun()
            
            # URL checkboxes
            for i, url in enumerate(st.session_state.discovered_sitemap_urls):
                is_selected = url in st.session_state.selected_sitemap_urls
                
                if st.checkbox(url, value=is_selected, key=f"url_cb_{i}"):
                    st.session_state.selected_sitemap_urls.add(url)
                else:
                    st.session_state.selected_sitemap_urls.discard(url)
            
            selected_count = len(st.session_state.selected_sitemap_urls)
            total_count = len(st.session_state.discovered_sitemap_urls)
            st.caption(f"{selected_count}/{total_count} URLs selected")
    
    async def _render_direct_crawl(self) -> None:
        """Render direct crawling functionality."""
        st.markdown("**Option B: Crawl and Scrape Starting from URL**")
        
        crawl_url = st.text_input(
            "Starting URL for crawl:",
            key="crawl_start_url",
            placeholder="https://example.com/start"
        )
        
        crawl_limit = st.number_input(
            "Max pages to crawl:",
            min_value=1,
            max_value=50,
            value=5,
            key="crawl_limit"
        )
        
        return crawl_url, crawl_limit
    
    async def _render_docsend_section(self) -> None:
        """Render the DocSend deck processing section."""
        st.subheader("5. DocSend Presentation Decks (Optional)")
        st.write("Extract text from DocSend presentation slides using OCR")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            docsend_url = st.text_input(
                "DocSend URL:",
                key="docsend_url",
                placeholder="https://docsend.com/view/..."
            )
        
        with col2:
            docsend_email = st.text_input(
                "Email:",
                key="docsend_email",
                placeholder="your@email.com"
            )
        
        docsend_password = st.text_input(
            "Password (if required):",
            key="docsend_password",
            type="password",
            placeholder="Optional password"
        )
        
        # Show status if DocSend content is cached
        if st.session_state.get('docsend_content'):
            docsend_metadata = st.session_state.get('docsend_metadata', {})
            slides_processed = docsend_metadata.get('processed_slides', 0)
            total_slides = docsend_metadata.get('total_slides', 0)
            processing_time = docsend_metadata.get('processing_time', 0)
            
            st.success(f"✅ DocSend deck processed: {slides_processed}/{total_slides} slides ({processing_time:.1f}s)")
            
            with st.expander("📋 DocSend Processing Details", expanded=False):
                st.write(f"**URL:** {docsend_metadata.get('url', 'Unknown')}")
                st.write(f"**Total slides:** {total_slides}")
                st.write(f"**Slides with text:** {docsend_metadata.get('slides_with_text', 0)}")
                st.write(f"**Total characters:** {docsend_metadata.get('total_characters', 0):,}")
                st.write(f"**Processing time:** {processing_time:.1f} seconds")
                
                # Show preview of extracted content
                content_preview = st.session_state.docsend_content[:500]
                st.text_area("Content preview:", content_preview, height=100, disabled=True)
        
        elif docsend_url:
            st.info(f"📊 DocSend deck will be processed: {docsend_url}")
            if not docsend_email:
                st.warning("⚠️ Email is required for DocSend access")
        
        # Process DocSend button
        if st.button("🔄 Process DocSend Deck", key="process_docsend_btn"):
            if docsend_url and docsend_email:
                # Log DocSend input
                log_user_action(
                    user=st.session_state.get('username', 'UNKNOWN'),
                    role=st.session_state.get('role', 'N/A'),
                    action="DOCSEND_INPUT",
                    page="Interactive Research",
                    details=f"DocSend URL and credentials provided: {docsend_url}",
                    additional_context={
                        "docsend_url": docsend_url,
                        "email": docsend_email,
                        "password_provided": bool(docsend_password)
                    }
                )
                await self._process_docsend_deck(docsend_url, docsend_email, docsend_password)
            else:
                st.error("Please provide both DocSend URL and email")
    
    async def _process_docsend_deck(self, url: str, email: str, password: str = '') -> None:
        """Process DocSend deck with OCR."""
        try:
            from src.core.docsend_client import DocSendClient
            import os
            import threading
            
            with st.spinner("🔬 Processing DocSend deck... (might be slow, please have patience)"):
                # Initialize DocSend client
                tesseract_cmd = os.getenv('TESSERACT_CMD')
                docsend_client = DocSendClient(tesseract_cmd=tesseract_cmd)
                
                # Create progress tracking that's thread-safe
                progress_placeholder = st.empty()
                progress_data = {'percentage': 0, 'status': 'Starting...'}
                progress_lock = threading.Lock()
                
                def progress_callback(percentage, status):
                    """Thread-safe progress callback."""
                    try:
                        with progress_lock:
                            progress_data['percentage'] = percentage
                            progress_data['status'] = status
                        # Don't update UI from thread - will be handled by main thread
                    except Exception:
                        pass  # Ignore any threading issues
                
                # Start progress monitoring in main thread
                def update_progress():
                    try:
                        with progress_lock:
                            percentage = progress_data['percentage']
                            status = progress_data['status']
                        progress_placeholder.progress(percentage / 100, text=status)
                    except Exception:
                        pass
                
                # Process DocSend with thread-safe progress
                result = await docsend_client.fetch_docsend_async(
                    url=url,
                    email=email,
                    password=password if password else None,
                    progress_callback=progress_callback
                )
                
                # Final progress update
                update_progress()
                progress_placeholder.empty()
                
                if result.get('success'):
                    docsend_content = result['content']
                    docsend_metadata = result['metadata']
                    
                    # Cache the results
                    st.session_state.docsend_content = docsend_content
                    st.session_state.docsend_metadata = docsend_metadata
                    
                    slides_processed = docsend_metadata.get('processed_slides', 0)
                    total_slides = docsend_metadata.get('total_slides', 0)
                    processing_time = docsend_metadata.get('processing_time', 0.0)
                    
                    # Log successful DocSend processing
                    log_docsend_processing(
                        user=st.session_state.get('username', 'UNKNOWN'),
                        role=st.session_state.get('role', 'N/A'),
                        docsend_url=url,
                        slides_processed=slides_processed,
                        total_slides=total_slides,
                        processing_time=processing_time,
                        success=True,
                        extracted_length=len(docsend_content)
                    )
                    
                    self.show_success(f"✅ DocSend processing complete: {slides_processed}/{total_slides} slides processed")
                    st.rerun()
                else:
                    error_msg = result.get('error', 'Unknown error')
                    
                    # Log failed DocSend processing
                    log_docsend_processing(
                        user=st.session_state.get('username', 'UNKNOWN'),
                        role=st.session_state.get('role', 'N/A'),
                        docsend_url=url,
                        slides_processed=0,
                        total_slides=0,
                        processing_time=0.0,
                        success=False,
                        extracted_length=0
                    )
                    
                    self.show_error(f"DocSend processing failed: {error_msg}")
                    
        except ImportError:
            self.show_error("DocSend dependencies not installed. Run: pip install -r requirements_docsend.txt")
            
            # Log import error
            log_docsend_processing(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                docsend_url=url,
                slides_processed=0,
                total_slides=0,
                processing_time=0.0,
                success=False,
                extracted_length=0
            )
            
        except Exception as e:
            self.show_error(f"DocSend processing error: {str(e)}")
            
            # Log exception in DocSend processing
            log_docsend_processing(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                docsend_url=url,
                slides_processed=0,
                total_slides=0,
                processing_time=0.0,
                success=False,
                extracted_length=0
            )
            
            # Add more detailed error logging
            import traceback
            print(f"DocSend processing exception: {traceback.format_exc()}")
    
    async def _render_report_generation(self) -> None:
        """Render the report generation section."""
        st.subheader("6. Generate Report")
        
        if st.button("Generate Unified Report", key="generate_report_btn"):
            await self._generate_report()
    
    async def _generate_report(self) -> None:
        """Generate the unified research report."""
        # Check if any input is provided
        research_query = st.session_state.get('research_query_input', '')
        has_docs = bool(st.session_state.processed_documents_content)
        has_urls = bool(st.session_state.get('urls_input', '').strip())
        has_crawl = bool(st.session_state.get('crawl_start_url', '').strip())
        has_selected_urls = bool(st.session_state.selected_sitemap_urls)
        has_docsend = bool(st.session_state.get('docsend_content', ''))
        
        if not (research_query or has_docs or has_urls or has_crawl or has_selected_urls or has_docsend):
            self.show_warning("Please provide a research query, upload documents, enter URLs, select crawling options, or process a DocSend deck.")
            return
        
        with st.spinner("Generating report..."):
            try:
                # Process URLs and content
                await self._process_web_content()
                
                # Generate AI report
                report_content = await self._call_ai_for_report()
                
                if report_content:
                    st.session_state.unified_report_content = report_content
                    st.session_state.report_generated_for_chat = True
                    
                    # Generate report ID for chat
                    report_id = f"report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S%f')}"
                    st.session_state.current_report_id_for_chat = report_id
                    
                    # Log report generation activity
                    username = st.session_state.get('username', 'UNKNOWN')
                    print(f"DEBUG: Report generated for username: {username}")  # Debug print
                    if username != 'UNKNOWN':
                        try:
                            print(f"DEBUG: Logging report generation activity...")  # Debug print
                            user_history_service.add_activity(
                                UserHistoryEntry(
                                    username=username,
                                    activity_type='report_generated',
                                    session_id=f"streamlit_{report_id}_{username}",
                                    report_id=report_id,
                                    details={
                                        'action': 'report_generated',
                                        'report_length': len(report_content),
                                        'has_documents': bool(st.session_state.processed_documents_content),
                                        'has_web_content': bool(st.session_state.scraped_web_content or st.session_state.crawled_web_content),
                                        'has_docsend': bool(st.session_state.get('docsend_content'))
                                    }
                                )
                            )
                            print(f"DEBUG: Report generation activity logged successfully")  # Debug print
                        except Exception as e:
                            print(f"DEBUG: Error logging report generation: {e}")  # Debug print
                    
                    # Build RAG context
                    await self._build_rag_context(report_id)
                    
                    self.show_success("Report generated successfully!")
                else:
                    self.show_error("Failed to generate report. AI returned empty response.")
                    
            except Exception as e:
                self.show_error(f"Error generating report: {str(e)}")
        
        st.rerun()
    
    async def _process_web_content(self) -> None:
        """Process web content from URLs or crawling."""
        # Clear previous content
        st.session_state.scraped_web_content = []
        st.session_state.crawled_web_content = []
        
        # Process selected sitemap URLs or manual URLs
        urls_to_scrape = []
        
        if st.session_state.selected_sitemap_urls:
            urls_to_scrape = list(st.session_state.selected_sitemap_urls)
        elif st.session_state.get('urls_input', '').strip():
            urls_to_scrape = [url.strip() for url in st.session_state.urls_input.split('\n') if url.strip()]
        
        if urls_to_scrape:
            st.info(f"Scraping {len(urls_to_scrape)} URLs...")
            scraped_data = await self._scrape_urls(urls_to_scrape)
            st.session_state.scraped_web_content = scraped_data
        
        # Handle crawling if no specific URLs and crawl URL provided
        crawl_url = st.session_state.get('crawl_start_url', '').strip()
        if crawl_url and not urls_to_scrape:
            crawl_limit = st.session_state.get('crawl_limit', 5)
            st.info(f"Crawling from {crawl_url} (limit: {crawl_limit})...")
            crawled_data = await self._crawl_site(crawl_url, crawl_limit)
            st.session_state.crawled_web_content = crawled_data
    
    async def _scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Scrape content from specific URLs."""
        if not st.session_state.firecrawl_client:
            return []
        
        try:
            import time
            start_time = time.time()
            
            results = await st.session_state.firecrawl_client.scrape_multiple_urls(urls)
            processed_results = []
            success_count = 0
            failed_count = 0
            
            for result in results:
                url = result.get("metadata", {}).get("url", result.get("url", "unknown"))
                if result.get("success", False):
                    content = result.get("data", {}).get("content", "")
                    if not content:
                        content = result.get("content", "")
                    processed_results.append({"url": url, "content": content, "status": "success"})
                    success_count += 1
                else:
                    error = result.get("error", "Unknown error")
                    processed_results.append({"url": url, "error": error, "status": "failed"})
                    failed_count += 1
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Log web scraping activity
            log_web_scraping(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                urls=urls,
                success_count=success_count,
                failed_count=failed_count,
                processing_time=processing_time
            )
            
            return processed_results
        except Exception as e:
            # Log failed web scraping
            log_web_scraping(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                urls=urls,
                success_count=0,
                failed_count=len(urls),
                processing_time=0.0
            )
            
            self.show_error(f"Error scraping URLs: {str(e)}")
            return []
    
    async def _crawl_site(self, start_url: str, limit: int) -> List[Dict[str, Any]]:
        """Crawl site starting from URL."""
        # Simplified crawling implementation
        try:
            scraped_data = await self._scrape_urls([start_url])
            return scraped_data
        except Exception as e:
            self.show_error(f"Error crawling site: {str(e)}")
            return []
    
    async def _call_ai_for_report(self) -> str:
        """Call AI to generate the report."""
        if not st.session_state.openrouter_client:
            return ""
        
        # Prepare content
        research_query = st.session_state.get('research_query_input', '')
        
        # Combine document content
        doc_content = []
        for doc in st.session_state.processed_documents_content:
            doc_content.append(f"--- Document: {doc['name']} ---\n{doc['text']}\n---")
        combined_docs = "\n".join(doc_content)
        
        # Combine web content
        web_content = []
        for item in st.session_state.scraped_web_content:
            if item.get("status") == "success" and item.get("content"):
                web_content.append(f"--- URL: {item['url']} ---\n{item['content']}\n---")
        
        for item in st.session_state.crawled_web_content:
            if item.get("status") == "success" and item.get("content"):
                web_content.append(f"--- Crawled: {item['url']} ---\n{item['content']}\n---")
        
        combined_web = "\n".join(web_content)
        
        # Add DocSend content
        docsend_content = st.session_state.get('docsend_content', '')
        docsend_metadata = st.session_state.get('docsend_metadata', {})
        
        # Build prompt
        if research_query:
            prompt = f"Research Query: {research_query}\n\n"
        else:
            prompt = "Please generate a comprehensive report based on the provided content.\n\n"
        
        if combined_docs:
            prompt += f"Document Content:\n{combined_docs}\n\n"
        
        if combined_web:
            prompt += f"Web Content:\n{combined_web}\n\n"
        
        if docsend_content:
            slides_processed = docsend_metadata.get('processed_slides', 0)
            total_slides = docsend_metadata.get('total_slides', 0)
            docsend_url = docsend_metadata.get('url', 'Unknown')
            
            prompt += f"DocSend Presentation Content:\n"
            prompt += f"--- DocSend Deck: {docsend_url} ({slides_processed}/{total_slides} slides processed) ---\n"
            prompt += f"{docsend_content}\n\n"
        
        prompt += "Based on the above content, please generate a comprehensive research report."
        
        try:
            model_to_use = st.session_state.get("selected_model", OPENROUTER_PRIMARY_MODEL)
            system_prompt = st.session_state.get("system_prompt", "You are a helpful research assistant.")
            
            # Record start time for processing time calculation
            start_time = time.time()
            
            response = await st.session_state.openrouter_client.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                model_override=model_to_use
            )
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Log AI interaction
            log_ai_interaction(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                model=model_to_use,
                prompt=prompt,
                response=response or "",
                processing_time=processing_time,
                page="Interactive Research",
                success=bool(response)
            )
            
            return response or ""
            
        except Exception as e:
            # Log failed AI interaction
            log_ai_interaction(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                model=st.session_state.get("selected_model", OPENROUTER_PRIMARY_MODEL),
                prompt=prompt,
                response="",
                processing_time=0.0,
                page="Interactive Research",
                success=False
            )
            
            self.show_error(f"Error calling AI: {str(e)}")
            return ""
    
    async def _build_rag_context(self, report_id: str) -> None:
        """Build RAG context for the report."""
        try:
            embedding_model = get_embedding_model()
            
            # Combine all text for RAG
            all_text = []
            
            if st.session_state.unified_report_content:
                all_text.append(st.session_state.unified_report_content)
            
            for doc in st.session_state.processed_documents_content:
                all_text.append(f"--- Document: {doc['name']} ---\n{doc['text']}")
            
            for item in st.session_state.scraped_web_content:
                if item.get("status") == "success" and item.get("content"):
                    all_text.append(f"--- Web: {item['url']} ---\n{item['content']}")
            
            # Add DocSend content to RAG
            docsend_content = st.session_state.get('docsend_content', '')
            if docsend_content:
                docsend_metadata = st.session_state.get('docsend_metadata', {})
                docsend_url = docsend_metadata.get('url', 'Unknown')
                all_text.append(f"--- DocSend: {docsend_url} ---\n{docsend_content}")
            
            combined_text = "\n\n---\n\n".join(all_text)
            text_chunks = split_text_into_chunks(combined_text)
            
            if text_chunks:
                faiss_index = build_faiss_index(text_chunks, embedding_model)
                if faiss_index:
                    st.session_state.rag_contexts[report_id] = {
                        "index": faiss_index,
                        "chunks": text_chunks,
                        "embedding_model_name": DEFAULT_EMBEDDING_MODEL
                    }
                    self.show_success(f"RAG context built with {len(text_chunks)} chunks")
                else:
                    st.session_state.rag_contexts[report_id] = None
            else:
                st.session_state.rag_contexts[report_id] = None
                
        except Exception as e:
            self.show_error(f"Error building RAG context: {str(e)}")
            st.session_state.rag_contexts[report_id] = None
    
    async def _render_report_display(self) -> None:
        """Render the generated report display."""
        if st.session_state.get('unified_report_content'):
            st.markdown("---")
            st.subheader("Generated Report")
            st.markdown(st.session_state.unified_report_content)
            
            st.download_button(
                label="Download Report",
                data=st.session_state.unified_report_content,
                file_name="research_report.md",
                mime="text/markdown",
                key="download_report_btn"
            )
    
    async def _render_admin_panel(self) -> None:
        """Render comprehensive admin panel if user is admin."""
        if st.session_state.get("role") == "admin":
            st.markdown("---")
            st.subheader("🔧 Admin Panel")
            
            # Environment Status
            import os
            required_vars = ["OPENROUTER_API_KEY"]
            optional_vars = ["FIRECRAWL_API_URL", "REDIS_URL", "TESSERACT_CMD"]
            
            missing_required = [var for var in required_vars if not os.getenv(var)]
            missing_optional = [var for var in optional_vars if not os.getenv(var)]
            
            if missing_required:
                st.error(f"❌ Missing required environment variables: {', '.join(missing_required)}")
            else:
                st.success("✅ Required environment configured correctly")
            
            if missing_optional:
                st.warning(f"⚠️ Optional environment variables not set: {', '.join(missing_optional)}")
            
            # System Status Section
            st.markdown("### 📊 **System Status**")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Document processing stats
                docs_processed = len(st.session_state.get('processed_documents_content', []))
                st.metric("Documents Processed", docs_processed)
                
                # Web content stats
                web_scraped = len(st.session_state.get('scraped_web_content', []))
                web_crawled = len(st.session_state.get('crawled_web_content', []))
                total_web = web_scraped + web_crawled
                st.metric("Web Sources", total_web)
            
            with col2:
                # DocSend status
                docsend_processed = 1 if st.session_state.get('docsend_content') else 0
                st.metric("DocSend Decks", docsend_processed)
                
                # Reports generated
                reports_generated = 1 if st.session_state.get('unified_report_content') else 0
                st.metric("Reports Generated", reports_generated)
            
            with col3:
                # RAG contexts
                rag_contexts = len(st.session_state.get('rag_contexts', {}))
                st.metric("RAG Contexts", rag_contexts)
                
                # Current model
                current_model = st.session_state.get('selected_model', 'Not Set')
                model_display = current_model.split('/')[-1] if '/' in current_model else current_model
                st.metric("Current AI Model", model_display)
            
            st.markdown("---")
            
            # Cache Management Section
            st.markdown("### 🗃️ **Cache Management**")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**Document Cache**")
                if st.button("🗑️ Clear Documents", key="admin_clear_docs"):
                    st.session_state.processed_documents_content = []
                    st.session_state.uploaded_files_content = []
                    self.show_success("Document cache cleared!")
            
            with col2:
                st.markdown("**Web Content Cache**")
                if st.button("🗑️ Clear Web Content", key="admin_clear_web"):
                    st.session_state.scraped_web_content = []
                    st.session_state.crawled_web_content = []
                    st.session_state.sitemap_urls = []
                    st.session_state.selected_sitemap_urls = set()
                    self.show_success("Web content cache cleared!")
            
            with col3:
                st.markdown("**DocSend Cache**")
                if st.button("🗑️ Clear DocSend", key="admin_clear_docsend"):
                    st.session_state.docsend_content = ""
                    st.session_state.docsend_metadata = {}
                    self.show_success("DocSend cache cleared!")
            
            # System-wide cache clear
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🧹 Clear All Caches", key="admin_clear_all", type="primary"):
                    # Clear all research-related session state
                    cache_keys = [
                        'processed_documents_content', 'uploaded_files_content',
                        'scraped_web_content', 'crawled_web_content',
                        'docsend_content', 'docsend_metadata',
                        'unified_report_content', 'rag_contexts',
                        'sitemap_urls', 'selected_sitemap_urls',
                        'research_query_input', 'urls_input'
                    ]
                    for key in cache_keys:
                        if key in st.session_state:
                            if 'content' in key and key.endswith('_content'):
                                st.session_state[key] = [] if isinstance(st.session_state[key], list) else ""
                            elif 'contexts' in key:
                                st.session_state[key] = {}
                            elif 'urls' in key:
                                st.session_state[key] = [] if 'selected' not in key else set()
                            else:
                                st.session_state[key] = [] if isinstance(st.session_state[key], list) else ""
                    
                    self.show_success("All caches cleared successfully!")
            
            with col2:
                if st.button("🔄 Reset Session", key="admin_reset_session"):
                    # Reset to initial state but keep authentication
                    auth_keys = ['authenticated', 'username', 'role', 'system_prompt']
                    auth_values = {key: st.session_state.get(key) for key in auth_keys}
                    
                    # Clear all session state
                    for key in list(st.session_state.keys()):
                        if key not in auth_keys:
                            del st.session_state[key]
                    
                    # Restore authentication
                    for key, value in auth_values.items():
                        if value is not None:
                            st.session_state[key] = value
                    
                    self.show_success("Session reset! Page will reload.")
                    st.rerun()
            
            st.markdown("---")
            
            # Client Status Section
            st.markdown("### 🔌 **Client Status**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**OpenRouter Client**")
                openrouter_status = "✅ Connected" if st.session_state.get('openrouter_client') else "❌ Not Connected"
                st.write(openrouter_status)
                
                if st.button("🔄 Reconnect OpenRouter", key="admin_reconnect_openrouter"):
                    self._init_clients()
                    if st.session_state.get('openrouter_client'):
                        self.show_success("OpenRouter client reconnected!")
                    else:
                        self.show_error("Failed to reconnect OpenRouter client")
            
            with col2:
                st.markdown("**Firecrawl Client**")
                firecrawl_status = "✅ Connected" if st.session_state.get('firecrawl_client') else "❌ Not Connected"
                st.write(firecrawl_status)
                
                if st.button("🔄 Reconnect Firecrawl", key="admin_reconnect_firecrawl"):
                    self._init_clients()
                    if st.session_state.get('firecrawl_client'):
                        self.show_success("Firecrawl client reconnected!")
                    else:
                        self.show_warning("Firecrawl client not available (optional)")
            
            st.markdown("---")
            
            # System Information
            st.markdown("### ℹ️ **System Information**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Session Information**")
                st.code(f"""
Session ID: {id(st.session_state)}
User: {st.session_state.get('username', 'Unknown')}
Role: {st.session_state.get('role', 'Unknown')}
Page: Interactive Research
                """)
            
            with col2:
                st.markdown("**Environment Information**")
                import platform
                st.code(f"""
Platform: {platform.system()} {platform.release()}
Python: {platform.python_version()}
Streamlit: {st.__version__}
                """)
            
            # Debug Information (expandable)
            with st.expander("🐛 Debug Information", expanded=False):
                st.markdown("**Session State Keys**")
                session_keys = list(st.session_state.keys())
                st.write(f"Total keys: {len(session_keys)}")
                
                # Group keys by category
                auth_keys = [k for k in session_keys if any(x in k.lower() for x in ['auth', 'user', 'role', 'login'])]
                research_keys = [k for k in session_keys if any(x in k.lower() for x in ['research', 'document', 'web', 'docsend', 'report'])]
                client_keys = [k for k in session_keys if any(x in k.lower() for x in ['client', 'openrouter', 'firecrawl'])]
                other_keys = [k for k in session_keys if k not in auth_keys + research_keys + client_keys]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Authentication Keys**")
                    for key in auth_keys:
                        st.code(f"• {key}")
                    
                    st.markdown("**Research Keys**")
                    for key in research_keys[:10]:  # Limit display
                        st.code(f"• {key}")
                    if len(research_keys) > 10:
                        st.caption(f"... and {len(research_keys) - 10} more")
                
                with col2:
                    st.markdown("**Client Keys**")
                    for key in client_keys:
                        st.code(f"• {key}")
                    
                    st.markdown("**Other Keys**")
                    for key in other_keys[:10]:  # Limit display
                        st.code(f"• {key}")
                    if len(other_keys) > 10:
                        st.caption(f"... and {len(other_keys) - 10} more")
    
    async def _render_chat_interface(self) -> None:
        """Render chat interface if report is generated."""
        if (st.session_state.get("report_generated_for_chat") and 
            st.session_state.get("current_report_id_for_chat")):
            
            st.markdown("---")
            with st.expander("💬 Chat with AI about this Report", expanded=False):
                report_id = st.session_state.current_report_id_for_chat
                
                st.success("💬 **Chat Ready** - Ask questions about your research report, documents, and web sources!")
                
                # Chat input
                user_question = st.text_input(
                    "Ask a question about the report:",
                    key="interactive_chat_input",
                    placeholder="What are the key findings? Can you summarize the main points?"
                )
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button("💬 Ask", key="interactive_chat_ask_btn"):
                        if user_question:
                            # Log chat question input
                            log_user_action(
                                user=st.session_state.get('username', 'UNKNOWN'),
                                role=st.session_state.get('role', 'N/A'),
                                action="CHAT_QUESTION_INPUT",
                                page="Interactive Research - Chat",
                                details=f"Chat question asked: {user_question[:100]}{'...' if len(user_question) > 100 else ''}",
                                additional_context={
                                    "question_length": len(user_question),
                                    "question_words": len(user_question.split()),
                                    "report_id": report_id
                                }
                            )
                            await self._process_chat_question(user_question, report_id)
                        else:
                            st.warning("Please enter a question.")
                
                with col2:
                    if st.button("🧹 Clear Chat", key="interactive_clear_chat_btn"):
                        if 'interactive_chat_sessions' not in st.session_state:
                            st.session_state.interactive_chat_sessions = {}
                        st.session_state.interactive_chat_sessions[report_id] = []
                        self.show_success("Chat cleared!")
                
                # Display chat history
                self._display_chat_history(report_id)
    
    async def _process_chat_question(self, question: str, report_id: str) -> None:
        """Process a chat question using RAG context or direct AI analysis."""
        try:
            with st.spinner("🤔 AI is thinking..."):
                # Initialize chat sessions if not exists
                if 'interactive_chat_sessions' not in st.session_state:
                    st.session_state.interactive_chat_sessions = {}
                if report_id not in st.session_state.interactive_chat_sessions:
                    st.session_state.interactive_chat_sessions[report_id] = []
                    
                    # Log session creation for new chat sessions
                    username = st.session_state.get('username', 'UNKNOWN')
                    print(f"DEBUG: New chat session for username: {username}")  # Debug print
                    if username != 'UNKNOWN':
                        try:
                            session_id = f"streamlit_{report_id}_{username}"
                            print(f"DEBUG: Logging session creation for: {session_id}")  # Debug print
                            user_history_service.log_session_created(username, session_id, report_id)
                            print(f"DEBUG: Session creation logged successfully")  # Debug print
                        except Exception as e:
                            print(f"DEBUG: Error logging session creation: {e}")  # Debug print
                
                rag_context = st.session_state.get('rag_contexts', {}).get(report_id)
                client = st.session_state.get('openrouter_client')
                
                if not client:
                    self.show_error("OpenRouter client not available")
                    return
                
                response_method = "Direct Analysis"
                
                if rag_context:
                    # RAG-based response (preferred when available)
                    try:
                        from src.core.rag_utils import get_embedding_model, search_faiss_index, TOP_K_RESULTS
                        
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
                    # Direct analysis using all available content
                    relevant_content = self._get_relevant_content_for_question(question)
                    
                    prompt = f"""Based on the research content provided below, please answer the user's question.

Research Content:
{relevant_content}

Question: {question}

Please provide a comprehensive answer based on the research content."""
                    
                    system_prompt = st.session_state.get("system_prompt", "You are a helpful research assistant.")
                
                # Get AI response
                model_to_use = st.session_state.get("selected_model", "openai/gpt-4o")
                
                start_time = time.time()
                response = await client.generate_response(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model_override=model_to_use
                )
                processing_time = time.time() - start_time
                
                if response:
                    # Log successful chat interaction
                    log_ai_interaction(
                        user=st.session_state.get('username', 'UNKNOWN'),
                        role=st.session_state.get('role', 'N/A'),
                        model=model_to_use,
                        prompt=prompt,
                        response=response,
                        processing_time=processing_time,
                        page="Interactive Research - Chat",
                        success=True
                    )
                    
                    # Log to user history service
                    username = st.session_state.get('username', 'UNKNOWN')
                    print(f"DEBUG: Chat response for username: {username}")  # Debug print
                    if username != 'UNKNOWN':
                        try:
                            # Generate or get session ID for this report
                            session_id = f"streamlit_{report_id}_{username}"
                            print(f"DEBUG: Logging chat message for session: {session_id}")  # Debug print
                            
                            user_history_service.log_chat_message(
                                username=username,
                                session_id=session_id,
                                report_id=report_id,
                                query=question,
                                response=response
                            )
                            print(f"DEBUG: Chat message logged successfully")  # Debug print
                        except Exception as e:
                            print(f"DEBUG: Error logging chat message: {e}")  # Debug print
                    
                    # Add to chat history
                    chat_entry = {
                        "question": question,
                        "answer": response,
                        "method": response_method,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                    st.session_state.interactive_chat_sessions[report_id].append(chat_entry)
                    
                    # Clear input
                    st.session_state.interactive_chat_input = ""
                    st.rerun()
                else:
                    # Log failed chat interaction
                    log_ai_interaction(
                        user=st.session_state.get('username', 'UNKNOWN'),
                        role=st.session_state.get('role', 'N/A'),
                        model=model_to_use,
                        prompt=prompt,
                        response="",
                        processing_time=processing_time,
                        page="Interactive Research - Chat",
                        success=False
                    )
                    self.show_error("Failed to get AI response")
                    
        except Exception as e:
            # Log chat processing error
            log_user_action(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="CHAT_PROCESSING_ERROR",
                page="Interactive Research - Chat",
                details=f"Chat processing failed: {str(e)}",
                additional_context={
                    "question": question[:200] + "..." if len(question) > 200 else question,
                    "error": str(e),
                    "report_id": report_id
                }
            )
            self.show_error(f"Error processing chat question: {str(e)}")
    
    def _get_relevant_content_for_question(self, question: str) -> str:
        """Get relevant content for answering the question."""
        content_parts = []
        
        # Add report content
        if st.session_state.get('unified_report_content'):
            content_parts.append(f"--- Generated Report ---\n{st.session_state.unified_report_content}")
        
        # Add document content
        for doc in st.session_state.get('processed_documents_content', []):
            content_parts.append(f"--- Document: {doc['name']} ---\n{doc['text']}")
        
        # Add web content
        for item in st.session_state.get('scraped_web_content', []):
            if item.get("status") == "success" and item.get("content"):
                content_parts.append(f"--- Web: {item['url']} ---\n{item['content']}")
        
        for item in st.session_state.get('crawled_web_content', []):
            if item.get("status") == "success" and item.get("content"):
                content_parts.append(f"--- Crawled: {item['url']} ---\n{item['content']}")
        
        # Add DocSend content
        docsend_content = st.session_state.get('docsend_content', '')
        if docsend_content:
            docsend_metadata = st.session_state.get('docsend_metadata', {})
            docsend_url = docsend_metadata.get('url', 'Unknown')
            content_parts.append(f"--- DocSend: {docsend_url} ---\n{docsend_content}")
        
        return "\n\n".join(content_parts)
    
    def _display_chat_history(self, report_id: str) -> None:
        """Display chat history for the report."""
        if 'interactive_chat_sessions' not in st.session_state:
            st.session_state.interactive_chat_sessions = {}
        
        chat_history = st.session_state.interactive_chat_sessions.get(report_id, [])
        
        if chat_history:
            st.markdown("### 💬 Chat History")
            
            for i, entry in enumerate(reversed(chat_history[-10:])):  # Show last 10 messages
                with st.container():
                    st.markdown(f"**🙋 Question ({entry['timestamp']}):**")
                    st.markdown(f"> {entry['question']}")
                    
                    st.markdown(f"**🤖 Answer ({entry['method']}):**")
                    st.markdown(entry['answer'])
                    
                    if i < len(chat_history) - 1:
                        st.markdown("---")
            
            if len(chat_history) > 10:
                st.caption(f"Showing last 10 of {len(chat_history)} messages")
        else:
            st.info("No chat history yet. Ask a question to get started!") 