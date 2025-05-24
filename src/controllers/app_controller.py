"""
App Controller for AI Research Agent.
Manages page routing, authentication, and overall application flow.
"""

import streamlit as st
import yaml
import bcrypt
import os
from pathlib import Path
from typing import Dict, Any, Optional

from src.config import USERS_CONFIG_PATH, DEFAULT_PROMPTS, SYSTEM_PROMPT
from src.audit_logger import get_audit_logger
from src.pages.interactive_research import InteractiveResearchPage
from src.pages.notion_automation import NotionAutomationPage
from src.pages.research_lab import ResearchLabPage

class AppController:
    """Main application controller for page routing and state management."""
    
    def __init__(self):
        self.pages = {
            "Interactive Research": InteractiveResearchPage(),
            "Notion Automation": NotionAutomationPage(),
            "Research Lab": ResearchLabPage()
        }
        self.current_page = None
    
    async def run(self) -> None:
        """Main application entry point."""
        # Set page configuration
        st.set_page_config(
            page_title="AI Research Agent",
            page_icon="🤖",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Initialize session state
        self._init_global_session_state()
        
        # Render sidebar (authentication and navigation)
        await self._render_sidebar()
        
        # Render main content area
        await self._render_main_content()
    
    def _init_global_session_state(self) -> None:
        """Initialize global session state variables."""
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if "username" not in st.session_state:
            st.session_state.username = None
        if "role" not in st.session_state:
            st.session_state.role = None
        if "show_signup" not in st.session_state:
            st.session_state.show_signup = False
        if "system_prompt" not in st.session_state:
            st.session_state.system_prompt = SYSTEM_PROMPT
        if "current_page" not in st.session_state:
            st.session_state.current_page = "Interactive Research"
    
    async def _render_sidebar(self) -> None:
        """Render the sidebar with authentication and navigation."""
        with st.sidebar:
            st.title("AI Research Agent")
            st.markdown("---")
            
            if not st.session_state.authenticated:
                await self._render_authentication()
            else:
                await self._render_user_panel()
                await self._render_navigation()
    
    async def _render_authentication(self) -> None:
        """Render authentication forms (login/signup)."""
        if st.session_state.show_signup:
            await self._render_signup_form()
        else:
            await self._render_login_form()
    
    async def _render_login_form(self) -> None:
        """Render the login form."""
        st.subheader("Login")
        
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Login", key="login_btn", use_container_width=True):
                await self._handle_login(username, password)
        
        with col2:
            if st.button("Sign Up", key="show_signup_btn", use_container_width=True):
                st.session_state.show_signup = True
                st.rerun()
    
    async def _render_signup_form(self) -> None:
        """Render the signup form."""
        st.subheader("Create Account")
        
        username = st.text_input("Username", key="signup_username")
        password = st.text_input("Password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Create Account", key="signup_btn", use_container_width=True):
                await self._handle_signup(username, password, confirm_password)
        
        with col2:
            if st.button("Back to Login", key="back_to_login_btn", use_container_width=True):
                st.session_state.show_signup = False
                st.rerun()
    
    async def _render_user_panel(self) -> None:
        """Render the user panel for authenticated users."""
        st.subheader("User Panel")
        st.write(f"👤 **User**: {st.session_state.username}")
        st.write(f"🔑 **Role**: {st.session_state.get('role', 'Unknown')}")
        
        if st.button("Logout", key="logout_btn", use_container_width=True):
            await self._handle_logout()
        
        # System prompt editor
        st.markdown("---")
        st.subheader("System Prompt")
        
        new_prompt = st.text_area(
            "Edit session system prompt:",
            value=st.session_state.system_prompt,
            height=200,
            key="system_prompt_editor"
        )
        
        if new_prompt != st.session_state.system_prompt:
            st.session_state.system_prompt = new_prompt
            st.success("System prompt updated!")
            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="SYSTEM_PROMPT_UPDATED",
                details="User updated session system prompt"
            )
    
    async def _render_navigation(self) -> None:
        """Render page navigation."""
        st.markdown("---")
        st.subheader("Navigation")
        
        # Page selector
        page_names = list(self.pages.keys())
        current_index = page_names.index(st.session_state.current_page) if st.session_state.current_page in page_names else 0
        
        selected_page = st.selectbox(
            "Select Feature:",
            options=page_names,
            index=current_index,
            key="page_selector"
        )
        
        if selected_page != st.session_state.current_page:
            st.session_state.current_page = selected_page
            st.rerun()
        
        # Show page description
        current_page_obj = self.pages.get(st.session_state.current_page)
        if current_page_obj:
            st.caption(f"📄 {current_page_obj.get_page_title()}")
    
    async def _render_main_content(self) -> None:
        """Render the main content area."""
        if not st.session_state.authenticated:
            self._render_welcome_page()
        else:
            await self._render_selected_page()
    
    def _render_welcome_page(self) -> None:
        """Render welcome page for unauthenticated users."""
        st.title("🤖 AI Research Agent")
        st.markdown("---")
        
        st.markdown("""
        ## Welcome to AI Research Agent
        
        A powerful research automation platform that combines:
        
        ### 🔍 Interactive Research
        - **Document Analysis**: Upload and analyze PDFs, DOCX, TXT, and Markdown files
        - **Web Scraping**: Extract content from specific URLs or crawl entire websites
        - **AI-Powered Reports**: Generate comprehensive research reports using advanced AI models
        - **Smart Chat**: Ask questions about your research with RAG-powered responses
        
        ### 🤖 Notion Automation
        - **CRM Integration**: Monitor and automate Notion database workflows
        - **Automated Research**: Run scheduled research pipelines on new entries
        - **Smart Scoring**: Automatically score and rate projects or opportunities
        - **Real-time Monitoring**: Track database changes and trigger actions
        
        ### 🚀 Key Features
        - **Multi-Model Support**: Choose from various AI models (GPT, Claude, Qwen, etc.)
        - **Document Processing**: Advanced text extraction and analysis
        - **Web Intelligence**: Sitemap scanning and intelligent crawling
        - **User Management**: Role-based access with audit logging
        - **Flexible Architecture**: Modular design for easy extension
        
        ---
        
        **Please log in or create an account to get started →**
        """)
        
        # Show some stats or features
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Supported Formats", "PDF, DOCX, TXT, MD")
        
        with col2:
            st.metric("AI Models", "6+ Models Available")
        
        with col3:
            st.metric("Integrations", "Notion, Firecrawl, OpenRouter")
    
    async def _render_selected_page(self) -> None:
        """Render the currently selected page."""
        current_page_name = st.session_state.current_page
        page_obj = self.pages.get(current_page_name)
        
        if page_obj:
            try:
                await page_obj.render()
            except Exception as e:
                st.error(f"Error rendering page '{current_page_name}': {str(e)}")
                get_audit_logger(
                    user=st.session_state.get('username', 'UNKNOWN'),
                    role=st.session_state.get('role', 'N/A'),
                    action="PAGE_RENDER_ERROR",
                    details=f"Error rendering page {current_page_name}: {str(e)}"
                )
        else:
            st.error(f"Page '{current_page_name}' not found.")
    
    async def _handle_login(self, username: str, password: str) -> None:
        """Handle user login."""
        if not username or not password:
            st.error("Please enter both username and password.")
            return
        
        users = self._load_users()
        user_data = users.get(username, {})
        
        if user_data and self._verify_password(password, user_data.get("password", "")):
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.role = user_data.get("role", "researcher")
            
            # Load user-specific system prompt
            user_prompt = user_data.get("system_prompt")
            if not user_prompt:
                user_prompt = DEFAULT_PROMPTS.get(st.session_state.role, SYSTEM_PROMPT)
            st.session_state.system_prompt = user_prompt
            
            st.success("Login successful!")
            get_audit_logger(
                user=username,
                role=st.session_state.role,
                action="USER_LOGIN_SUCCESS",
                details=f"User {username} logged in successfully"
            )
            st.rerun()
        else:
            st.error("Invalid username or password.")
            get_audit_logger(
                user=username or "UNKNOWN",
                role="N/A",
                action="USER_LOGIN_FAILURE",
                details=f"Failed login attempt for username: '{username}'"
            )
    
    async def _handle_signup(self, username: str, password: str, confirm_password: str) -> None:
        """Handle user signup."""
        if not username or not password:
            st.error("Username and password cannot be empty.")
            return
        
        if password != confirm_password:
            st.error("Passwords do not match.")
            return
        
        users = self._load_users()
        
        if username in users:
            st.error("Username already exists.")
            return
        
        # Create new user
        users[username] = {
            "password": self._hash_password(password),
            "role": "researcher",  # Default role
            "system_prompt": DEFAULT_PROMPTS.get("researcher", SYSTEM_PROMPT)
        }
        
        if self._save_users(users):
            st.success("Account created successfully! Please log in.")
            get_audit_logger(
                user=username,
                role="researcher",
                action="USER_SIGNUP_SUCCESS",
                details=f"New user account created: {username}"
            )
            st.session_state.show_signup = False
            st.rerun()
        else:
            st.error("Failed to create account. Please try again.")
    
    async def _handle_logout(self) -> None:
        """Handle user logout."""
        username = st.session_state.username
        role = st.session_state.get("role", "N/A")
        
        # Clear session state
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.role = None
        st.session_state.system_prompt = SYSTEM_PROMPT
        st.session_state.show_signup = False
        st.session_state.current_page = "Interactive Research"
        
        get_audit_logger(
            user=username,
            role=role,
            action="USER_LOGOUT",
            details=f"User {username} logged out"
        )
        
        st.success("Logged out successfully!")
        st.rerun()
    
    def _load_users(self) -> Dict[str, Any]:
        """Load user data from YAML file."""
        if not os.path.exists(USERS_CONFIG_PATH):
            # Initialize with default users if file doesn't exist
            try:
                from src.init_users import init_users
                init_users()
            except Exception as e:
                st.warning(f"Could not initialize default users: {e}")
                return {}
        
        try:
            with open(USERS_CONFIG_PATH, 'r') as f:
                users = yaml.safe_load(f) or {}
                return users
        except Exception as e:
            st.error(f"Error loading user data: {e}")
            return {}
    
    def _save_users(self, users_data: Dict[str, Any]) -> bool:
        """Save user data to YAML file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(USERS_CONFIG_PATH), exist_ok=True)
            
            with open(USERS_CONFIG_PATH, 'w') as f:
                yaml.dump(users_data, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            st.error(f"Failed to save user data: {e}")
            return False
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        try:
            return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        except Exception:
            return False
    
    def _hash_password(self, password: str) -> str:
        """Hash password with bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() 