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
from src.models.chat_models import ChatSession, ChatHistoryItem

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
        self.log_page_access()
        
        # Initialize session state
        self._init_session_state()
        
        # Initialize clients
        self._init_clients()
        
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
        
        # Admin panel (if admin)
        await self._render_admin_panel()
        
        # Chat interface
        await self._render_chat_interface()
    
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
                    else:
                        self.show_error(f"Failed to extract content from: {file_data.name}")
                        
                except Exception as e:
                    self.show_error(f"Error processing {file_data.name}: {str(e)}")
            
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
        
        try:
            with st.spinner(f"Scanning {site_url} for sitemap URLs..."):
                discovered_urls = await discover_sitemap_urls(site_url)
            
            st.session_state.discovered_sitemap_urls = discovered_urls
            st.session_state.sitemap_scan_completed = True
            
            if discovered_urls:
                self.show_success(f"Found {len(discovered_urls)} URLs!")
            else:
                self.show_info("No URLs found in sitemap.")
                
        except Exception as e:
            error_msg = f"Sitemap scan failed: {str(e)}"
            st.session_state.sitemap_scan_error = error_msg
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
        
        if not (research_query or has_docs or has_urls or has_crawl or has_selected_urls):
            self.show_warning("Please provide a research query, upload documents, enter URLs, or select options for crawling.")
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
            results = await st.session_state.firecrawl_client.scrape_multiple_urls(urls)
            processed_results = []
            
            for result in results:
                url = result.get("metadata", {}).get("url", result.get("url", "unknown"))
                if result.get("success", False):
                    content = result.get("data", {}).get("content", "")
                    if not content:
                        content = result.get("content", "")
                    processed_results.append({"url": url, "content": content, "status": "success"})
                else:
                    error = result.get("error", "Unknown error")
                    processed_results.append({"url": url, "error": error, "status": "failed"})
            
            return processed_results
        except Exception as e:
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
        
        # Build prompt
        if research_query:
            prompt = f"Research Query: {research_query}\n\n"
        else:
            prompt = "Please generate a comprehensive report based on the provided content.\n\n"
        
        if combined_docs:
            prompt += f"Document Content:\n{combined_docs}\n\n"
        
        if combined_web:
            prompt += f"Web Content:\n{combined_web}\n\n"
        
        prompt += "Based on the above content, please generate a comprehensive research report."
        
        try:
            model_to_use = st.session_state.get("selected_model", OPENROUTER_PRIMARY_MODEL)
            system_prompt = st.session_state.get("system_prompt", "You are a helpful research assistant.")
            
            response = await st.session_state.openrouter_client.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                model_override=model_to_use
            )
            
            return response or ""
            
        except Exception as e:
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
        """Render admin panel if user is admin."""
        if st.session_state.get("role") == "admin":
            st.markdown("---")
            st.subheader("Admin Panel")
            st.info("Admin panel features would be implemented here.")
    
    async def _render_chat_interface(self) -> None:
        """Render chat interface if report is generated."""
        if (st.session_state.get("report_generated_for_chat") and 
            st.session_state.get("current_report_id_for_chat")):
            
            st.markdown("---")
            with st.expander("💬 Chat with AI about this Report", expanded=False):
                st.info("Chat interface would be implemented here.")
                # Chat implementation would go here 