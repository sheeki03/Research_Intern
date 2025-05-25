"""
Research Lab Page - Advanced Research Interface with Enhanced Features
Combines Notion automation with sophisticated research capabilities from routers/models.
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
import uuid
import aiohttp
import logging
from enum import Enum

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
from src.models.chat_models import ChatSession, ChatHistoryItem, ChatMessageInput, ChatMessageOutput

# Enhanced Research State Management
class ResearchState(Enum):
    IDLE = "idle"
    AWAITING_QUERY = "awaiting_query"
    AWAITING_BREADTH = "awaiting_breadth"
    AWAITING_DEPTH = "awaiting_depth"
    ASKING_QUESTIONS = "asking_questions"
    RESEARCHING = "researching"
    COMPLETE = "complete"

# Cache configuration
CACHE_DURATION_HOURS = 6
CACHE_FILE_PATH = "cache/notion_pages_cache.pkl"

class ResearchLabPage(BasePage):
    """Advanced Research Lab with enhanced features and FastAPI integration."""
    
    def __init__(self):
        super().__init__("research_lab", "Research Lab")
        # Initialize logger
        self.logger = logging.getLogger(__name__)
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
        """Render the Research Lab page."""
        if not self.check_authentication():
            self.show_auth_required_message()
            return
        
        # Log page access
        self.log_page_access()
        
        # Initialize session state
        self._init_session_state()
        
        # Initialize clients
        self._init_clients()
        
        # Show page header with enhanced features badge
        self.show_page_header("🧪 Advanced Research Lab - Enhanced Features & FastAPI Integration")
        
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
        
        # Enhanced Feature Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "## 🔬 **Multi-Step Research**", 
            "## 📋 **Notion Integration**", 
            "## 💬 **Enhanced Chat**", 
            "## 🚀 **Research Pipeline**",
            "## 🔧 **Admin & API**"
        ])
        
        with tab1:
            await self._render_multi_step_research()
        
        with tab2:
            await self._render_notion_integration()
        
        with tab3:
            await self._render_enhanced_chat()
        
        with tab4:
            await self._render_research_pipeline()
        
        with tab5:
            await self._render_admin_api_panel()
    
    def _init_session_state(self) -> None:
        """Initialize enhanced session state keys."""
        required_keys = {
            # Existing Notion functionality
            'notion_polling_active': False,
            'notion_last_poll_time': None,
            'notion_automation_logs': [],
            'notion_manual_research_running': False,
            'notion_available_pages': [],
            'notion_selected_pages': [],
            'notion_current_operation': None,
            'notion_operation_progress': {},
            'notion_last_poll_results': {},
            'notion_discovered_sitemap_urls': [],
            'notion_sitemap_scan_in_progress': False,
            'notion_sitemap_scan_error': None,
            'notion_sitemap_scan_completed': False,
            'notion_selected_sitemap_urls': set(),
            'notion_unified_report_content': "",
            'notion_report_generated_for_chat': False,
            'notion_current_report_id_for_chat': None,
            'notion_rag_contexts': {},
            'notion_processed_documents_content': [],
            'notion_last_uploaded_file_details': [],
            'notion_uploaded_docs': [],
            'notion_web_urls': [],
            'notion_crawl_option': None,
            'notion_crawl_url': '',
            'notion_crawl_sitemap_url': '',
            'notion_selected_model': 'qwen/qwen3-30b-a3b:free',
            'notion_auto_publish_to_notion': False,
            
            # Enhanced Research Lab features
            'lab_research_state': ResearchState.IDLE,
            'lab_current_query': '',
            'lab_research_breadth': 4,
            'lab_research_depth': 2,
            'lab_follow_up_questions': [],
            'lab_question_answers': [],
            'lab_current_question_index': 0,
            'lab_research_results': None,
            'lab_conversation_id': None,
            
            # Enhanced Chat with FastAPI models
            'lab_chat_sessions': {},  # Dict[str, ChatSession]
            'lab_active_chat_session': None,
            'lab_api_chat_enabled': False,
            
            # Multi-step research workflow
            'lab_workflow_step': 1,
            'lab_research_context': {},
            'lab_enhanced_prompts': [],
            
            # API Integration
            'lab_api_base_url': 'http://localhost:8000',
            'lab_api_connected': False,
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
    
    async def _render_multi_step_research(self) -> None:
        """Render enhanced multi-step research interface."""
        st.markdown("### 🔬 **Multi-Step AI Research (KitchenAI Pattern)**")
        st.info("Advanced research workflow with AI-guided questions and iterative improvement")
        
        current_state = st.session_state.get('lab_research_state', ResearchState.IDLE)
        
        # State display
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🔄 Current State", current_state.value.title())
        with col2:
            conversation_id = st.session_state.get('lab_conversation_id', 'None')
            st.metric("💭 Conversation ID", conversation_id[:8] if conversation_id != 'None' else 'None')
        with col3:
            questions_count = len(st.session_state.get('lab_follow_up_questions', []))
            st.metric("❓ Follow-up Questions", questions_count)
        
        # State machine for research flow
        if current_state == ResearchState.IDLE:
            await self._render_research_start()
        elif current_state == ResearchState.AWAITING_QUERY:
            await self._render_query_input()
        elif current_state == ResearchState.AWAITING_BREADTH:
            await self._render_breadth_input()
        elif current_state == ResearchState.AWAITING_DEPTH:
            await self._render_depth_input()
        elif current_state == ResearchState.ASKING_QUESTIONS:
            await self._render_follow_up_questions()
        elif current_state == ResearchState.RESEARCHING:
            await self._render_research_progress()
        elif current_state == ResearchState.COMPLETE:
            await self._render_research_results()
        
        # Reset button
        if st.button("🔄 Reset Research Flow", key="reset_research_flow"):
            self._reset_research_state()
            st.rerun()
    
    async def _render_research_start(self) -> None:
        """Render research start interface."""
        st.markdown("#### 🚀 **Start New Research Session**")
        
        if st.button("🔬 Begin Multi-Step Research", key="start_research"):
            # Generate new conversation ID
            st.session_state.lab_conversation_id = str(uuid.uuid4())
            st.session_state.lab_research_state = ResearchState.AWAITING_QUERY
            st.rerun()
    
    async def _render_query_input(self) -> None:
        """Render research query input."""
        st.markdown("#### 🎯 **Research Query**")
        
        query = st.text_area(
            "What would you like to research?",
            key="lab_research_query",
            height=100,
            placeholder="Example: 'Analyze the competitive landscape for DeFi lending protocols' or 'Evaluate STXN token economics and market positioning'"
        )
        
        if st.button("➡️ Continue", key="submit_query") and query:
            st.session_state.lab_current_query = query
            st.session_state.lab_research_state = ResearchState.AWAITING_BREADTH
            st.rerun()
    
    async def _render_breadth_input(self) -> None:
        """Render research breadth configuration."""
        st.markdown("#### 📊 **Research Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            breadth = st.number_input(
                "Research Breadth (2-10)",
                min_value=2,
                max_value=10,
                value=4,
                key="lab_breadth_input",
                help="Number of different sources/angles to explore"
            )
        
        with col2:
            if st.button("➡️ Continue", key="submit_breadth"):
                st.session_state.lab_research_breadth = breadth
                st.session_state.lab_research_state = ResearchState.AWAITING_DEPTH
                st.rerun()
    
    async def _render_depth_input(self) -> None:
        """Render research depth configuration."""
        st.markdown("#### 🔍 **Research Depth**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            depth = st.number_input(
                "Research Depth (1-5)",
                min_value=1,
                max_value=5,
                value=2,
                key="lab_depth_input",
                help="How deep to go into each source/topic"
            )
        
        with col2:
            if st.button("🧠 Generate Follow-up Questions", key="generate_questions"):
                with st.spinner("🤔 AI is generating intelligent follow-up questions..."):
                    st.session_state.lab_research_depth = depth
                    await self._generate_follow_up_questions()
                    st.session_state.lab_research_state = ResearchState.ASKING_QUESTIONS
                    st.rerun()
    
    async def _generate_follow_up_questions(self) -> None:
        """Generate AI follow-up questions based on the research query."""
        try:
            client = st.session_state.get('notion_openrouter_client')
            if not client:
                raise RuntimeError("OpenRouter client not available")
            
            query = st.session_state.lab_current_query
            
            prompt = f"""
Based on the research query: "{query}"

Generate 3-5 intelligent follow-up questions that would help refine and improve the research. 
These questions should:
1. Clarify scope and focus areas
2. Identify specific metrics or data points needed
3. Understand the context and use case
4. Determine timeline and priorities

Format as a simple numbered list:
1. Question 1
2. Question 2
etc.
"""
            
            response = await client.generate_response(
                prompt=prompt,
                system_prompt="You are a research strategist helping to refine research queries with intelligent follow-up questions.",
                model_override=st.session_state.get('notion_selected_model', 'qwen/qwen3-30b-a3b:free')
            )
            
            # Parse questions from response
            questions = []
            for line in response.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                    # Remove numbering and clean up
                    question = re.sub(r'^\d+\.?\s*', '', line)
                    question = re.sub(r'^[-•]\s*', '', question)
                    if question:
                        questions.append(question)
            
            st.session_state.lab_follow_up_questions = questions
            st.session_state.lab_question_answers = []
            st.session_state.lab_current_question_index = 0
            
        except Exception as e:
            self.show_error(f"Failed to generate follow-up questions: {str(e)}")
            # Fallback to default questions
            st.session_state.lab_follow_up_questions = [
                "What is the primary use case or goal for this research?",
                "What specific metrics or data points are most important?",
                "What is the timeline for this research?"
            ]
    
    async def _render_follow_up_questions(self) -> None:
        """Render follow-up questions interface."""
        st.markdown("#### ❓ **Follow-up Questions**")
        
        questions = st.session_state.get('lab_follow_up_questions', [])
        answers = st.session_state.get('lab_question_answers', [])
        current_idx = st.session_state.get('lab_current_question_index', 0)
        
        if current_idx < len(questions):
            st.markdown(f"**Question {current_idx + 1} of {len(questions)}:**")
            st.info(questions[current_idx])
            
            answer = st.text_area(
                "Your answer:",
                key=f"question_answer_{current_idx}",
                height=100
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("➡️ Next Question", key="next_question") and answer:
                    # Store answer
                    if len(answers) <= current_idx:
                        answers.append(answer)
                    else:
                        answers[current_idx] = answer
                    
                    st.session_state.lab_question_answers = answers
                    st.session_state.lab_current_question_index = current_idx + 1
                    st.rerun()
            
            with col2:
                if st.button("⏭️ Skip Question", key="skip_question"):
                    # Store empty answer
                    if len(answers) <= current_idx:
                        answers.append("")
                    
                    st.session_state.lab_question_answers = answers
                    st.session_state.lab_current_question_index = current_idx + 1
                    st.rerun()
        
        else:
            # All questions answered
            st.success("✅ All questions completed!")
            
            # Show summary
            with st.expander("# 📋 **Question Summary**", expanded=True):
                for i, (q, a) in enumerate(zip(questions, answers)):
                    st.markdown(f"**Q{i+1}:** {q}")
                    st.markdown(f"**A{i+1}:** {a or '_Skipped_'}")
                    st.divider()
            
            if st.button("🔬 Start Enhanced Research", key="start_enhanced_research"):
                st.session_state.lab_research_state = ResearchState.RESEARCHING
                await self._execute_enhanced_research()
                st.rerun()
    
    async def _execute_enhanced_research(self) -> None:
        """Execute the enhanced research with all collected information."""
        try:
            with st.spinner("🔬 Executing enhanced research..."):
                # Combine query with Q&A context
                base_query = st.session_state.lab_current_query
                questions = st.session_state.get('lab_follow_up_questions', [])
                answers = st.session_state.get('lab_question_answers', [])
                
                enhanced_query = f"""
Primary Research Query: {base_query}

Additional Context from Follow-up Questions:
"""
                
                for q, a in zip(questions, answers):
                    if a:  # Only include answered questions
                        enhanced_query += f"\nQ: {q}\nA: {a}\n"
                
                # Get configuration
                breadth = st.session_state.get('lab_research_breadth', 4)
                depth = st.session_state.get('lab_research_depth', 2)
                
                # Execute research (using existing research functionality)
                client = st.session_state.get('notion_openrouter_client')
                model = st.session_state.get('notion_selected_model', 'qwen/qwen3-30b-a3b:free')
                
                # Generate comprehensive research report
                research_prompt = f"""
Conduct comprehensive research based on the following enhanced query:

{enhanced_query}

Research Configuration:
- Breadth: {breadth} (explore {breadth} different angles/sources)
- Depth: {depth} (depth level {depth} analysis)

Provide a detailed research report covering:
1. Executive Summary
2. Key Findings
3. Market Analysis
4. Technology/Product Analysis
5. Competitive Landscape
6. Risk Assessment
7. Opportunities and Recommendations
8. Data Sources and References

Format as a comprehensive markdown report with clear sections and bullet points.
"""
                
                report_content = await client.generate_response(
                    prompt=research_prompt,
                    system_prompt="You are an expert research analyst. Provide thorough, data-driven analysis with specific insights and actionable recommendations.",
                    model_override=model
                )
                
                # Store results
                st.session_state.lab_research_results = {
                    'enhanced_query': enhanced_query,
                    'report_content': report_content,
                    'breadth': breadth,
                    'depth': depth,
                    'timestamp': datetime.now().isoformat(),
                    'model_used': model
                }
                
                st.session_state.lab_research_state = ResearchState.COMPLETE
                
                # Also store in unified report for compatibility
                st.session_state.notion_unified_report_content = report_content
                st.session_state.notion_report_generated_for_chat = True
                
                # Generate report ID for chat
                report_id = f"lab_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S%f')}"
                st.session_state.notion_current_report_id_for_chat = report_id
                
        except Exception as e:
            self.show_error(f"Enhanced research failed: {str(e)}")
            st.session_state.lab_research_state = ResearchState.COMPLETE
    
    async def _render_research_progress(self) -> None:
        """Render research progress interface."""
        st.markdown("#### 🔬 **Research in Progress**")
        
        # Show animated progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        steps = [
            "Analyzing enhanced query...",
            "Gathering research sources...",
            "Processing information...",
            "Generating insights...",
            "Compiling final report..."
        ]
        
        for i, step in enumerate(steps):
            status_text.text(f"🔄 {step}")
            progress_bar.progress((i + 1) / len(steps))
            await asyncio.sleep(0.5)
        
        status_text.text("✅ Research completed!")
        
        # Auto-transition to results
        await asyncio.sleep(1)
        st.session_state.lab_research_state = ResearchState.COMPLETE
        st.rerun()
    
    async def _render_research_results(self) -> None:
        """Render research results interface."""
        st.markdown("#### 📊 **Research Results**")
        
        results = st.session_state.get('lab_research_results')
        if not results:
            st.error("No research results found.")
            return
        
        # Results metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🔍 Breadth", results.get('breadth', 'N/A'))
        with col2:
            st.metric("📊 Depth", results.get('depth', 'N/A'))
        with col3:
            st.metric("🤖 Model", results.get('model_used', 'N/A').split('/')[-1][:10])
        with col4:
            timestamp = results.get('timestamp', '')
            if timestamp:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
            else:
                time_str = "N/A"
            st.metric("🕐 Generated", time_str)
        
        # Enhanced Query Summary
        with st.expander("# 🎯 **Enhanced Query Used**", expanded=False):
            st.markdown(results.get('enhanced_query', 'No query available'))
        
        # Report Content
        st.markdown("### 📄 **Research Report**")
        report_content = results.get('report_content', '')
        
        if report_content:
            with st.expander("# 📖 **View Full Report**", expanded=True):
                st.markdown(report_content)
            
            # Download button
            st.download_button(
                label="📥 Download Research Report",
                data=report_content,
                file_name=f"enhanced_research_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                key="download_lab_report"
            )
            
            # Action buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔄 Start New Research", key="new_research"):
                    self._reset_research_state()
                    st.rerun()
            
            with col2:
                if st.button("💬 Chat About Report", key="chat_about_report"):
                    st.session_state.lab_active_chat_session = self._create_chat_session(
                        st.session_state.notion_current_report_id_for_chat
                    )
                    st.success("✅ Chat session created! Go to Enhanced Chat tab.")
            
            with col3:
                # Notion publishing option
                if st.button("📤 Publish to Notion", key="publish_lab_report"):
                    await self._publish_lab_report_to_notion()
        else:
            st.error("No report content generated.")
    
    def _reset_research_state(self) -> None:
        """Reset research state to start fresh."""
        st.session_state.lab_research_state = ResearchState.IDLE
        st.session_state.lab_current_query = ''
        st.session_state.lab_follow_up_questions = []
        st.session_state.lab_question_answers = []
        st.session_state.lab_current_question_index = 0
        st.session_state.lab_research_results = None
        st.session_state.lab_conversation_id = None
    
    async def _render_notion_integration(self) -> None:
        """Render Notion integration (copy from original)."""
        st.markdown("### 📋 **Notion CRM Integration**")
        st.info("Connect your research to Notion workspace with enhanced features")
        
        # All the original Notion functionality would go here
        # This is a placeholder - you can copy the relevant sections from notion_automation.py
        
        # Configuration section
        await self._render_configuration_section()
        
        # Page selection
        await self._render_page_selection_section()
        
        # Manual operations with enhanced publishing
        await self._render_manual_operations()
    
    async def _render_enhanced_chat(self) -> None:
        """Render enhanced chat interface with FastAPI models."""
        st.markdown("### 💬 **Enhanced Chat Interface**")
        st.info("Advanced chat with proper session management and FastAPI integration")
        
        # Chat session management
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🔗 **Session Management**")
            
            # Show active sessions
            sessions = st.session_state.get('lab_chat_sessions', {})
            if sessions:
                st.write(f"**Active Sessions:** {len(sessions)}")
                for session_id, session in sessions.items():
                    st.caption(f"📄 {session_id[:8]}... (Report: {session.report_id[:8]}...)")
            else:
                st.write("**No active sessions**")
            
            # Create new session
            if st.button("➕ New Chat Session", key="new_chat_session"):
                if st.session_state.get('notion_current_report_id_for_chat'):
                    session = self._create_chat_session(st.session_state.notion_current_report_id_for_chat)
                    st.session_state.lab_active_chat_session = session
                    st.success(f"✅ Created session: {session.session_id[:8]}...")
                    st.rerun()
                else:
                    st.warning("⚠️ Generate a report first to start a chat session")
        
        with col2:
            st.markdown("#### ⚙️ **Chat Configuration**")
            
            # API Integration toggle
            api_enabled = st.checkbox(
                "🚀 Enable FastAPI Integration",
                value=st.session_state.get('lab_api_chat_enabled', False),
                key="api_chat_toggle",
                help="Use FastAPI backend for enhanced chat features"
            )
            st.session_state.lab_api_chat_enabled = api_enabled
            
            if api_enabled:
                api_url = st.text_input(
                    "API Base URL:",
                    value=st.session_state.get('lab_api_base_url', 'http://localhost:8000'),
                    key="api_base_url"
                )
                st.session_state.lab_api_base_url = api_url
                
                if st.button("🔍 Test API Connection", key="test_api"):
                    await self._test_api_connection(api_url)
        
        # Active chat interface
        active_session = st.session_state.get('lab_active_chat_session')
        if active_session:
            await self._render_active_chat_session(active_session)
        else:
            st.info("💡 Create a new chat session or generate a report to start chatting")
    
    def _create_chat_session(self, report_id: str) -> ChatSession:
        """Create a new chat session using proper models."""
        session = ChatSession(report_id=report_id)
        
        # Store in session state
        if 'lab_chat_sessions' not in st.session_state:
            st.session_state.lab_chat_sessions = {}
        
        st.session_state.lab_chat_sessions[session.session_id] = session
        return session
    
    async def _render_active_chat_session(self, session: ChatSession) -> None:
        """Render active chat session interface."""
        st.markdown("---")
        st.markdown(f"#### 💬 **Active Chat Session**: `{session.session_id[:8]}...`")
        st.caption(f"📄 Report ID: `{session.report_id[:8]}...`")
        
        # Chat history
        if session.history:
            st.markdown("**Chat History:**")
            for item in session.history[-5:]:  # Show last 5 messages
                if item.role == "user":
                    st.markdown(f"🙋 **You:** {item.content}")
                else:
                    st.markdown(f"🤖 **AI:** {item.content}")
                st.divider()
        
        # Chat input
        col1, col2 = st.columns([4, 1])
        
        with col1:
            user_message = st.text_input(
                "Ask a question about the report:",
                key="enhanced_chat_input",
                placeholder="What are the key findings?"
            )
        
        with col2:
            if st.button("💬 Send", key="send_enhanced_chat"):
                if user_message:
                    await self._process_enhanced_chat_message(session, user_message)
                    st.rerun()
        
        # Session actions
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🧹 Clear History", key="clear_chat_history"):
                session.history = []
                st.session_state.lab_chat_sessions[session.session_id] = session
                st.rerun()
        
        with col2:
            if st.button("📤 Export Chat", key="export_chat"):
                await self._export_chat_session(session)
        
        with col3:
            if st.button("🗑️ Delete Session", key="delete_chat_session"):
                del st.session_state.lab_chat_sessions[session.session_id]
                st.session_state.lab_active_chat_session = None
                st.rerun()
    
    async def _process_enhanced_chat_message(self, session: ChatSession, message: str) -> None:
        """Process chat message with enhanced features."""
        try:
            # Add user message to history
            session.history.append(ChatHistoryItem(role="user", content=message))
            
            # Check if FastAPI integration is enabled
            if st.session_state.get('lab_api_chat_enabled', False):
                await self._process_via_api(session, message)
            else:
                await self._process_via_local(session, message)
            
            # Update session in storage
            st.session_state.lab_chat_sessions[session.session_id] = session
            
        except Exception as e:
            self.show_error(f"Chat processing failed: {str(e)}")
    
    async def _process_via_api(self, session: ChatSession, message: str) -> None:
        """Process chat message via FastAPI backend."""
        try:
            api_url = st.session_state.get('lab_api_base_url', 'http://localhost:8000')
            
            # Create ChatMessageInput
            chat_input = ChatMessageInput(
                user_query=message,
                report_id=session.report_id,
                session_id=session.session_id
            )
            
            # Make API request
            async with aiohttp.ClientSession() as client:
                async with client.post(
                    f"{api_url}/chat/ask",
                    json=chat_input.dict(),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        ai_response = result.get('ai_response', 'No response from API')
                        
                        # Add AI response to history
                        session.history.append(ChatHistoryItem(role="ai", content=ai_response))
                        self.show_success("✅ Response received via FastAPI")
                    else:
                        error_text = await response.text()
                        raise Exception(f"API error {response.status}: {error_text}")
                        
        except Exception as e:
            # Fallback to local processing
            st.warning(f"⚠️ API processing failed: {str(e)}. Falling back to local processing.")
            await self._process_via_local(session, message)
    
    async def _process_via_local(self, session: ChatSession, message: str) -> None:
        """Process chat message locally (fallback)."""
        try:
            # Use existing RAG functionality
            report_id = session.report_id
            rag_context = st.session_state.get('notion_rag_contexts', {}).get(report_id)
            
            if rag_context:
                # RAG-based response
                embedding_model = get_embedding_model()
                relevant_chunks = search_faiss_index(
                    message,
                    rag_context["index"],
                    rag_context["chunks"],
                    embedding_model,
                    top_k=TOP_K_RESULTS
                )
                
                context = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
                
                prompt = f"""Based on the following context from the research report, please answer the user's question.
                
Context:
{context}

Question: {message}

Please provide a helpful and accurate answer based on the context provided."""
                
                client = st.session_state.get('notion_openrouter_client')
                if client:
                    model = st.session_state.get('notion_selected_model', 'qwen/qwen3-30b-a3b:free')
                    ai_response = await client.generate_response(
                        prompt=prompt,
                        system_prompt="You are a helpful research assistant. Answer questions based on the provided context.",
                        model_override=model
                    )
                else:
                    ai_response = "OpenRouter client not available"
            else:
                # Simple echo response
                ai_response = f"Echo: You asked about report '{session.report_id[:8]}...': '{message}'"
            
            # Add AI response to history
            session.history.append(ChatHistoryItem(role="ai", content=ai_response))
            
        except Exception as e:
            # Ultimate fallback
            session.history.append(ChatHistoryItem(
                role="ai", 
                content=f"I encountered an error processing your message: {str(e)}"
            ))
    
    async def _test_api_connection(self, api_url: str) -> None:
        """Test connection to FastAPI backend."""
        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(f"{api_url}/") as response:
                    if response.status == 200:
                        st.session_state.lab_api_connected = True
                        self.show_success("✅ API connection successful!")
                    else:
                        st.session_state.lab_api_connected = False
                        self.show_error(f"❌ API connection failed: {response.status}")
        except Exception as e:
            st.session_state.lab_api_connected = False
            self.show_error(f"❌ API connection failed: {str(e)}")
    
    async def _export_chat_session(self, session: ChatSession) -> None:
        """Export chat session to file."""
        export_data = {
            "session_id": session.session_id,
            "report_id": session.report_id,
            "history": [{"role": item.role, "content": item.content} for item in session.history],
            "exported_at": datetime.now().isoformat()
        }
        
        export_json = json.dumps(export_data, indent=2)
        
        st.download_button(
            label="📥 Download Chat Export",
            data=export_json,
            file_name=f"chat_session_{session.session_id[:8]}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key="download_chat_export"
        )
    
    async def _render_research_pipeline(self) -> None:
        """Render enhanced research pipeline."""
        st.markdown("### 🚀 **Enhanced Research Pipeline**")
        st.info("Advanced research automation with Notion integration and multi-source analysis")
        
        # Copy enhanced research functionality from notion_automation.py
        # This would include all the document upload, URL scraping, etc.
        await self._render_additional_research_sources()
    
    async def _render_admin_api_panel(self) -> None:
        """Render admin and API management panel."""
        st.markdown("### 🔧 **Admin & API Management**")
        
        if st.session_state.get("role") == "admin":
            # Admin controls
            st.markdown("#### 👑 **Admin Controls**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**🗃️ Cache Management**")
                if st.button("🗑️ Clear All Caches", key="admin_clear_all_cache"):
                    await self._clear_all_caches()
                
                st.markdown("**🔄 System Reset**")
                if st.button("🔄 Reset Research Lab", key="admin_reset_lab"):
                    await self._reset_research_lab()
            
            with col2:
                st.markdown("**📊 System Statistics**")
                self._display_system_stats()
        
        # API Management
        st.markdown("#### 🔌 **API Management**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**FastAPI Status**")
            api_connected = st.session_state.get('lab_api_connected', False)
            if api_connected:
                st.success("✅ FastAPI Connected")
            else:
                st.error("❌ FastAPI Disconnected")
            
            if st.button("🔄 Refresh API Status", key="refresh_api_status"):
                await self._test_api_connection(st.session_state.get('lab_api_base_url', 'http://localhost:8000'))
                st.rerun()
        
        with col2:
            st.markdown("**Chat Router Status**")
            # Show router endpoints
            st.code("""
Available Endpoints:
- POST /chat/ask
- GET /chat/{session_id}/history
            """)
    
    async def _clear_all_caches(self) -> None:
        """Clear all cache files."""
        try:
            cache_files = [
                CACHE_FILE_PATH,
                "cache/reports_cache.pkl",
                "cache/sessions_cache.pkl"
            ]
            
            for cache_file in cache_files:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            
            # Clear session state caches
            for key in list(st.session_state.keys()):
                if 'cache' in key.lower() or 'temp' in key.lower():
                    del st.session_state[key]
            
            self.show_success("✅ All caches cleared successfully!")
            
        except Exception as e:
            self.show_error(f"Failed to clear caches: {str(e)}")
    
    async def _reset_research_lab(self) -> None:
        """Reset the entire research lab state."""
        try:
            # Reset research state
            self._reset_research_state()
            
            # Clear chat sessions
            st.session_state.lab_chat_sessions = {}
            st.session_state.lab_active_chat_session = None
            
            # Clear other lab states
            lab_keys = [key for key in st.session_state.keys() if key.startswith('lab_')]
            for key in lab_keys:
                if key != 'lab_api_base_url':  # Keep API URL
                    del st.session_state[key]
            
            # Re-initialize
            self._init_session_state()
            
            self.show_success("✅ Research Lab reset successfully!")
            
        except Exception as e:
            self.show_error(f"Failed to reset Research Lab: {str(e)}")
    
    def _display_system_stats(self) -> None:
        """Display system statistics."""
        # Calculate stats
        total_sessions = len(st.session_state.get('lab_chat_sessions', {}))
        total_logs = len(st.session_state.get('notion_automation_logs', []))
        reports_generated = 1 if st.session_state.get('lab_research_results') else 0
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("💬 Chat Sessions", total_sessions)
        with col2:
            st.metric("📊 Reports Generated", reports_generated)
        with col3:
            st.metric("📝 Total Logs", total_logs)
    
    # Copy utility methods from notion_automation.py
    def _init_clients(self) -> None:
        """Initialize API clients."""
        if "notion_openrouter_client" not in st.session_state:
            openrouter_client = OpenRouterClient()
            firecrawl_client = FirecrawlClient(redis_url=None)
            st.session_state.notion_openrouter_client = openrouter_client
            st.session_state.notion_firecrawl_client = firecrawl_client
    
    # Additional methods from notion_automation.py
    async def _render_configuration_section(self) -> None:
        """Render configuration section for Notion integration."""
        st.markdown("#### ⚙️ **Configuration**")
        st.info("🚧 Notion configuration section - coming soon!")
        
        # Basic model selection
        model_options = [
            'qwen/qwen3-30b-a3b:free',
            'qwen/qwen3-235b-a22b:free',
            'anthropic/claude-sonnet-4',
            'openai/gpt-4-turbo',
            'mistralai/mistral-7b-instruct:free'
        ]
        
        selected_model = st.selectbox(
            "Select AI Model:",
            options=model_options,
            index=0,
            key="notion_model_selector"
        )
        st.session_state.notion_selected_model = selected_model
    
    async def _render_page_selection_section(self) -> None:
        """Render page selection section for Notion integration."""
        st.markdown("#### 📄 **Page Selection**")
        st.info("🚧 Notion page selection - coming soon!")
        
        # Placeholder for page selection
        st.write("This section will allow you to:")
        st.write("- Select Notion pages for analysis")
        st.write("- Configure research parameters") 
        st.write("- Set up automation rules")
    
    async def _render_manual_operations(self) -> None:
        """Render manual operations section."""
        st.markdown("#### 🔧 **Manual Operations**")
        st.info("🚧 Manual operations - coming soon!")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔍 Manual Research", key="manual_research_btn"):
                st.info("Manual research functionality coming soon!")
        
        with col2:
            if st.button("📊 Generate Report", key="generate_report_btn"):
                st.info("Report generation functionality coming soon!")
        
        with col3:
            if st.button("📤 Publish to Notion", key="publish_notion_btn"):
                st.info("Notion publishing functionality coming soon!")
    
    async def _render_additional_research_sources(self) -> None:
        """Render additional research sources section."""
        st.markdown("#### 📚 **Additional Research Sources**")
        st.info("🚧 Additional research sources - coming soon!")
        
        # File upload
        uploaded_files = st.file_uploader(
            "Upload Documents:",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
            key="lab_file_upload"
        )
        
        # URL input
        url_input = st.text_input(
            "Web URLs (comma-separated):",
            key="lab_url_input",
            placeholder="https://example.com, https://another.com"
        )
        
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} files uploaded")
        
        if url_input:
            urls = [url.strip() for url in url_input.split(',') if url.strip()]
            st.success(f"✅ {len(urls)} URLs added")
    
    async def _publish_lab_report_to_notion(self) -> None:
        """Publish lab research report to Notion."""
        try:
            st.info("🚧 Notion publishing functionality coming soon!")
            # This would integrate with the existing Notion publishing logic
            # from notion_writer.py
        except Exception as e:
            self.show_error(f"Failed to publish to Notion: {str(e)}")
    