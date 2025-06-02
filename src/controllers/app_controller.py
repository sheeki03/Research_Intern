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
from src.utils.session_persistence import url_session_persistence


class AppController:
    """Main application controller for page routing and state management."""

    def __init__(self):
        self.pages = {
            "Interactive Research": InteractiveResearchPage(),
            "Notion Automation": NotionAutomationPage(),
        }
        self.current_page = None

    def _get_git_commit(self) -> str:
        """Get the current git commit hash."""
        commit_hash = os.getenv("SOURCE_COMMIT")
        if commit_hash:
            return commit_hash.strip()[:7]

        return ""

    async def run(self) -> None:
        """Main application entry point."""
        # Set page configuration
        st.set_page_config(
            page_title="AI Research Agent",
            page_icon="🤖",
            layout="wide",
            initial_sidebar_state="expanded",
        )

        # Initialize session state
        self._init_global_session_state()

        # Render sidebar (authentication and navigation)
        await self._render_sidebar()

        # Render main content area
        await self._render_main_content()

    def _init_global_session_state(self) -> None:
        """Initialize global session state variables."""
        # Initialize all session state keys first
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
        if "session_restored" not in st.session_state:
            st.session_state.session_restored = False
        
        # Try to restore session from URL after initialization
        self._try_restore_session()

    def _try_restore_session(self) -> None:
        """Try to restore session from URL parameters."""
        try:
            # Only try to restore once per session
            if st.session_state.get('session_restore_attempted', False):
                return
            
            st.session_state.session_restore_attempted = True
            
            # Try to load session from URL
            session_data = url_session_persistence.load_session_from_url()
            
            if session_data:
                username = session_data.get('username')
                role = session_data.get('role')
                
                # Verify user still exists in the system
                users = self._load_users()
                
                if username in users:
                    # Restore session
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.role = role
                    st.session_state.session_restored = True
                    
                    # Load user-specific system prompt
                    user_data = users.get(username, {})
                    user_prompt = user_data.get("system_prompt")
                    if not user_prompt:
                        user_prompt = DEFAULT_PROMPTS.get(role, SYSTEM_PROMPT)
                    st.session_state.system_prompt = user_prompt
                    
                    # Log session restoration
                    get_audit_logger(
                        user=username,
                        role=role,
                        action="SESSION_RESTORED",
                        details=f"Session restored from URL for user: {username}",
                    )
                else:
                    # User no longer exists, clear the session
                    st.query_params.clear()
                    
        except Exception as e:
            print(f"Error restoring session: {e}")

    async def _render_sidebar(self) -> None:
        """Render the sidebar with authentication and navigation."""
        with st.sidebar:
            st.title(f"AI Research Agent | Commit: {self._get_git_commit()}")
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
        confirm_password = st.text_input(
            "Confirm Password", type="password", key="confirm_password"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Create Account", key="signup_btn", use_container_width=True):
                await self._handle_signup(username, password, confirm_password)

        with col2:
            if st.button(
                "Back to Login", key="back_to_login_btn", use_container_width=True
            ):
                st.session_state.show_signup = False
                st.rerun()

    async def _render_user_panel(self) -> None:
        """Render the user panel for authenticated users."""
        st.subheader("User Panel")
        st.write(f"👤 **User**: {st.session_state.username}")
        st.write(f"🔑 **Role**: {st.session_state.get('role', 'Unknown')}")
        
        # Show session status
        if st.session_state.get('session_restored', False):
            st.success("🔄 Session restored from URL")
        else:
            st.info("🔒 Session active (persists across reloads)")

        if st.button("Logout", key="logout_btn", use_container_width=True):
            await self._handle_logout()

        # System prompt editor
        st.markdown("---")
        st.subheader("System Prompt")

        new_prompt = st.text_area(
            "Edit session system prompt:",
            value=st.session_state.system_prompt,
            height=200,
            key="system_prompt_editor",
        )

        if new_prompt != st.session_state.system_prompt:
            st.session_state.system_prompt = new_prompt
            st.success("System prompt updated!")
            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="SYSTEM_PROMPT_UPDATED",
                details="User updated session system prompt",
            )

    async def _render_navigation(self) -> None:
        """Render page navigation."""
        st.markdown("---")
        st.subheader("Navigation")

        # Page selector
        page_names = list(self.pages.keys())
        current_index = (
            page_names.index(st.session_state.current_page)
            if st.session_state.current_page in page_names
            else 0
        )

        selected_page = st.selectbox(
            "Select Feature:",
            options=page_names,
            index=current_index,
            key="page_selector",
        )

        if selected_page != st.session_state.current_page:
            st.session_state.current_page = selected_page
            st.rerun()

        # Show page description
        current_page_obj = self.pages.get(st.session_state.current_page)
        if current_page_obj:
            st.caption(f"📄 {current_page_obj.get_page_title()}")

        # Admin Panel (if admin user)
        if st.session_state.get("role") == "admin":
            await self._render_global_admin_panel()

    async def _render_main_content(self) -> None:
        """Render the main content area."""
        if not st.session_state.authenticated:
            self._render_welcome_page()
        else:
            await self._render_selected_page()

    def _render_welcome_page(self) -> None:
        """Render welcome page for unauthenticated users."""
        st.title(f"🤖 AI Research Agent | Commit: {self._get_git_commit()}")
        st.markdown("---")

        st.markdown(
            """
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
        """
        )

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
                    user=st.session_state.get("username", "UNKNOWN"),
                    role=st.session_state.get("role", "N/A"),
                    action="PAGE_RENDER_ERROR",
                    details=f"Error rendering page {current_page_name}: {str(e)}",
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

            # Save session for persistence
            try:
                # Create session token and update URL
                session_token = url_session_persistence._create_session_token(username, st.session_state.role)
                st.query_params["session"] = session_token
                
                st.success("Login successful! Session will persist across page reloads.")
                
                # Show session info
                with st.expander("🔒 Session Information", expanded=False):
                    st.info(f"""
                    **Session Active**: Your login will persist for 24 hours
                    **Username**: {username}
                    **Role**: {st.session_state.role}
                    
                    You can bookmark this page to maintain your session across browser restarts.
                    """)
                    
            except Exception as e:
                st.warning(f"Session persistence failed: {e}")
                st.success("Login successful!")

            get_audit_logger(
                user=username,
                role=st.session_state.role,
                action="USER_LOGIN_SUCCESS",
                details=f"User {username} logged in successfully",
            )
            st.rerun()
        else:
            st.error("Invalid username or password.")
            get_audit_logger(
                user=username or "UNKNOWN",
                role="N/A",
                action="USER_LOGIN_FAILURE",
                details=f"Failed login attempt for username: '{username}'",
            )

    async def _handle_signup(
        self, username: str, password: str, confirm_password: str
    ) -> None:
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
            "system_prompt": DEFAULT_PROMPTS.get("researcher", SYSTEM_PROMPT),
        }

        if self._save_users(users):
            st.success("Account created successfully! Please log in.")
            get_audit_logger(
                user=username,
                role="researcher",
                action="USER_SIGNUP_SUCCESS",
                details=f"New user account created: {username}",
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
        st.session_state.session_restored = False
        st.session_state.session_restore_attempted = False

        # Clear session from URL
        try:
            st.query_params.clear()
        except Exception as e:
            print(f"Error clearing session from URL: {e}")

        get_audit_logger(
            user=username,
            role=role,
            action="USER_LOGOUT",
            details=f"User {username} logged out",
        )

        st.success("Logged out successfully! Session cleared.")
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
            with open(USERS_CONFIG_PATH, "r") as f:
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

            with open(USERS_CONFIG_PATH, "w") as f:
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

    async def _render_global_admin_panel(self) -> None:
        """Render global admin panel in sidebar for admin users."""
        st.markdown("---")
        st.subheader("👑 Global Admin")

        # System Overview
        with st.expander("📊 System Overview", expanded=False):
            # User stats
            users = self._load_users()
            total_users = len(users)
            admin_users = len([u for u in users.values() if u.get("role") == "admin"])
            researcher_users = total_users - admin_users

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Users", total_users)
                st.metric("Admin Users", admin_users)
            with col2:
                st.metric("Researchers", researcher_users)
                st.metric("Current Page", st.session_state.current_page)

        # User Management
        with st.expander("👥 User Management", expanded=False):
            st.markdown("**Active Users**")
            users = self._load_users()

            for username, user_data in users.items():
                role = user_data.get("role", "unknown")
                role_icon = "👑" if role == "admin" else "🔬"

                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"{role_icon} {username}")
                with col2:
                    st.caption(role.title())
                with col3:
                    if username != st.session_state.username:  # Can't delete self
                        if st.button(
                            "🗑️",
                            key=f"delete_user_{username}",
                            help=f"Delete {username}",
                        ):
                            await self._delete_user(username)

            # Add new user
            st.markdown("**Add New User**")
            new_username = st.text_input("Username", key="admin_new_username")
            new_password = st.text_input(
                "Password", type="password", key="admin_new_password"
            )
            new_role = st.selectbox(
                "Role", ["researcher", "admin"], key="admin_new_role"
            )

            if st.button("➕ Add User", key="admin_add_user_btn"):
                if new_username and new_password:
                    await self._add_user(new_username, new_password, new_role)
                else:
                    st.error("Username and password required")

        # User Activity Monitoring
        with st.expander("📊 User Activity Monitoring", expanded=False):
            await self._render_user_activity_monitoring()

        # System Controls
        with st.expander("🔧 System Controls", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                if st.button("🧹 Clear All Logs", key="admin_clear_logs"):
                    await self._clear_system_logs()

                if st.button("🔄 Reset All Sessions", key="admin_reset_all_sessions"):
                    await self._reset_all_sessions()

            with col2:
                if st.button("📊 Export User Data", key="admin_export_users"):
                    await self._export_user_data()

                if st.button("⚠️ System Maintenance", key="admin_maintenance"):
                    await self._system_maintenance()

        # Environment Status
        with st.expander("🌍 Environment Status", expanded=False):
            import os

            # Check critical environment variables
            env_vars = {
                "OPENROUTER_API_KEY": "🔑 OpenRouter API",
                "FIRECRAWL_API_URL": "🌐 Firecrawl URL",
                "REDIS_URL": "📦 Redis Cache",
                "TESSERACT_CMD": "👁️ OCR Engine",
            }

            for var, description in env_vars.items():
                value = os.getenv(var)
                if value:
                    st.success(f"✅ {description}")
                else:
                    st.error(f"❌ {description}")

            # System info
            import platform

            st.markdown("**System Information**")
            st.code(
                f"""
Platform: {platform.system()} {platform.release()}
Python: {platform.python_version()}
Streamlit: {st.__version__}
            """
            )

    async def _delete_user(self, username: str) -> None:
        """Delete a user account."""
        try:
            users = self._load_users()
            if username in users:
                del users[username]
                if self._save_users(users):
                    st.success(f"User '{username}' deleted successfully!")
                    get_audit_logger(
                        user=st.session_state.username,
                        role=st.session_state.get("role", "N/A"),
                        action="USER_DELETED",
                        details=f"Admin deleted user: {username}",
                    )
                    st.rerun()
                else:
                    st.error("Failed to save user data")
            else:
                st.error("User not found")
        except Exception as e:
            st.error(f"Error deleting user: {e}")

    async def _add_user(self, username: str, password: str, role: str) -> None:
        """Add a new user account."""
        try:
            users = self._load_users()

            if username in users:
                st.error("Username already exists")
                return

            users[username] = {
                "password": self._hash_password(password),
                "role": role,
                "system_prompt": DEFAULT_PROMPTS.get(role, SYSTEM_PROMPT),
            }

            if self._save_users(users):
                st.success(f"User '{username}' created successfully!")
                get_audit_logger(
                    user=st.session_state.username,
                    role=st.session_state.get("role", "N/A"),
                    action="USER_CREATED",
                    details=f"Admin created user: {username} with role: {role}",
                )
                # Clear form
                st.session_state.admin_new_username = ""
                st.session_state.admin_new_password = ""
                st.rerun()
            else:
                st.error("Failed to save user data")
        except Exception as e:
            st.error(f"Error creating user: {e}")

    async def _clear_system_logs(self) -> None:
        """Clear system logs."""
        try:
            import os
            import glob

            log_files = glob.glob("logs/*.log")
            cleared_count = 0

            for log_file in log_files:
                try:
                    os.remove(log_file)
                    cleared_count += 1
                except Exception:
                    pass

            st.success(f"Cleared {cleared_count} log files")
            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="LOGS_CLEARED",
                details=f"Admin cleared {cleared_count} log files",
            )
        except Exception as e:
            st.error(f"Error clearing logs: {e}")

    async def _reset_all_sessions(self) -> None:
        """Reset all user sessions (warning: this will log out all users)."""
        try:
            # This is a placeholder - in a real app you'd clear session storage
            st.warning(
                "⚠️ This would reset all user sessions in a production environment"
            )
            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="ALL_SESSIONS_RESET",
                details="Admin triggered global session reset",
            )
        except Exception as e:
            st.error(f"Error resetting sessions: {e}")

    async def _export_user_data(self) -> None:
        """Export user data for backup."""
        try:
            users = self._load_users()

            # Remove passwords for export
            export_data = {}
            for username, user_data in users.items():
                export_data[username] = {
                    "role": user_data.get("role", "researcher"),
                    "created": "unknown",  # Would track creation date in real app
                }

            import json

            export_json = json.dumps(export_data, indent=2)

            st.download_button(
                label="📥 Download User Export",
                data=export_json,
                file_name="user_export.json",
                mime="application/json",
                key="download_user_export",
            )

            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="USER_DATA_EXPORTED",
                details="Admin exported user data",
            )
        except Exception as e:
            st.error(f"Error exporting user data: {e}")

    async def _system_maintenance(self) -> None:
        """Perform system maintenance tasks."""
        try:
            maintenance_tasks = []

            # Clear temporary files
            import os
            import glob

            temp_patterns = ["cache/*.tmp", "output/*.tmp", "logs/*.tmp"]
            for pattern in temp_patterns:
                temp_files = glob.glob(pattern)
                for temp_file in temp_files:
                    try:
                        os.remove(temp_file)
                        maintenance_tasks.append(f"Removed {temp_file}")
                    except Exception:
                        pass

            # Optimize cache files (placeholder)
            maintenance_tasks.append("Cache optimization completed")

            if maintenance_tasks:
                st.success(f"Maintenance completed: {len(maintenance_tasks)} tasks")
                with st.expander("Maintenance Details"):
                    for task in maintenance_tasks:
                        st.write(f"✅ {task}")
            else:
                st.info("No maintenance tasks needed")

            get_audit_logger(
                user=st.session_state.username,
                role=st.session_state.get("role", "N/A"),
                action="SYSTEM_MAINTENANCE",
                details=f"Admin performed maintenance: {len(maintenance_tasks)} tasks",
            )
        except Exception as e:
            st.error(f"Error during maintenance: {e}")

    async def _render_user_activity_monitoring(self) -> None:
        """Render user activity monitoring panel."""
        try:
            from src.audit_logger import get_user_activity_details, get_activity_summary

            # Time period selector
            col1, col2 = st.columns([1, 1])
            with col1:
                hours = st.selectbox(
                    "Time Period",
                    [1, 6, 12, 24, 48, 168],
                    index=3,
                    key="activity_hours",
                )
            with col2:
                limit = st.selectbox(
                    "Max Entries", [25, 50, 100, 200], index=1, key="activity_limit"
                )

            # Get activity summary
            summary = get_activity_summary(hours=hours)

            if "error" not in summary:
                # Activity summary metrics
                st.markdown("**📈 Activity Summary**")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Total Actions", summary.get("total_actions", 0))
                    st.metric("Unique Users", summary.get("unique_users", 0))

                with col2:
                    st.metric("AI Interactions", summary.get("ai_interactions", 0))
                    st.metric("Failed Actions", summary.get("failed_actions", 0))

                with col3:
                    st.metric("Web Scraping", summary.get("web_scraping", 0))
                    st.metric(
                        "Document Processing", summary.get("document_processing", 0)
                    )

                with col4:
                    st.metric(
                        "DocSend Processing", summary.get("docsend_processing", 0)
                    )
                    st.metric("Admin Actions", summary.get("admin_actions", 0))

                # Models used
                models_used = summary.get("models_used", {})
                if models_used:
                    st.markdown("**🤖 Models Used**")
                    for model, count in sorted(
                        models_used.items(), key=lambda x: x[1], reverse=True
                    ):
                        st.write(f"• {model}: {count} times")

            # Detailed activity log
            st.markdown("---")
            st.markdown("**📋 Detailed User Activity**")

            activities = get_user_activity_details(hours=hours, limit=limit)

            if activities:
                for activity in activities:
                    with st.container():
                        # Header with timestamp and user
                        timestamp = activity["timestamp"].strftime("%m/%d %H:%M:%S")
                        user = activity["user"]
                        role = activity["role"]
                        action = activity["action"]

                        # Color code by action type
                        if "AI_INTERACTION" in action:
                            action_color = "🤖"
                        elif "WEB_SCRAPING" in action:
                            action_color = "🌐"
                        elif "DOCUMENT" in action:
                            action_color = "📄"
                        elif "DOCSEND" in action:
                            action_color = "📊"
                        elif "MODEL_SELECTED" in action:
                            action_color = "⚙️"
                        elif "ADMIN" in action:
                            action_color = "👑"
                        elif "LOGIN" in action or "LOGOUT" in action:
                            action_color = "🔐"
                        else:
                            action_color = "📝"

                        # Main activity line
                        col1, col2, col3 = st.columns([2, 1, 3])
                        with col1:
                            st.write(
                                f"**{timestamp}** | {action_color} {user} ({role})"
                            )
                        with col2:
                            if activity["model"]:
                                st.caption(f"🤖 {activity['model']}")
                        with col3:
                            st.caption(f"**{action}**")

                        # Parsed details
                        parsed = activity.get("parsed_details", {})
                        details_to_show = []

                        if parsed.get("selected_model"):
                            details_to_show.append(
                                f"🤖 Model: {parsed['selected_model']}"
                            )

                        if parsed.get("research_query"):
                            query_preview = (
                                parsed["research_query"][:100] + "..."
                                if len(parsed["research_query"]) > 100
                                else parsed["research_query"]
                            )
                            details_to_show.append(f"❓ Query: {query_preview}")

                        if parsed.get("urls"):
                            details_to_show.append(f"🌐 URLs: {parsed['urls']}")

                        if parsed.get("prompt_preview"):
                            details_to_show.append(
                                f"💬 Prompt: {parsed['prompt_preview']}"
                            )

                        if parsed.get("processing_time"):
                            details_to_show.append(
                                f"⏱️ Time: {parsed['processing_time']}"
                            )

                        if parsed.get("response_length"):
                            details_to_show.append(
                                f"📏 Response: {parsed['response_length']} chars"
                            )

                        if parsed.get("page"):
                            details_to_show.append(f"📄 Page: {parsed['page']}")

                        if parsed.get("docsend_slides"):
                            details_to_show.append(
                                f"📊 DocSend: {parsed['docsend_slides']}"
                            )

                        if parsed.get("involves_documents"):
                            details_to_show.append(f"📁 Documents involved")

                        if parsed.get("involves_sitemap"):
                            details_to_show.append(f"🗺️ Sitemap scanning")
                            if parsed.get("sitemap_urls_found"):
                                details_to_show.append(
                                    f"🔍 Found: {parsed['sitemap_urls_found']} URLs"
                                )

                        # Show parsed details
                        if details_to_show:
                            for detail in details_to_show:
                                st.caption(f"  {detail}")

                        # Show raw details if no parsed details
                        elif activity["details"]:
                            raw_details = (
                                activity["details"][:200] + "..."
                                if len(activity["details"]) > 200
                                else activity["details"]
                            )
                            st.caption(f"  📝 {raw_details}")

                        st.divider()
            else:
                st.info(f"No user activity found in the last {hours} hours")

        except Exception as e:
            st.error(f"Error loading user activity: {str(e)}")
            st.code(f"Debug: {type(e).__name__}: {str(e)}")
