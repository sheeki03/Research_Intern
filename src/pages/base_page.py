"""
Base page class for AI Research Agent pages.
Provides common functionality and interface for all pages.
"""

import streamlit as st
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from src.audit_logger import get_audit_logger

class BasePage(ABC):
    """Base class for all application pages."""
    
    def __init__(self, page_name: str, page_title: str):
        self.page_name = page_name
        self.page_title = page_title
        
    @abstractmethod
    async def render(self) -> None:
        """Render the page content. Must be implemented by subclasses."""
        pass
    
    def get_page_name(self) -> str:
        """Get the page name."""
        return self.page_name
    
    def get_page_title(self) -> str:
        """Get the page title."""
        return self.page_title
    
    def log_page_access(self) -> None:
        """Log page access for audit purposes."""
        get_audit_logger(
            user=st.session_state.get('username', 'UNKNOWN'),
            role=st.session_state.get('role', 'N/A'),
            action="PAGE_ACCESS",
            details=f"User accessed page: {self.page_name}"
        )
    
    def check_authentication(self) -> bool:
        """Check if user is authenticated."""
        return st.session_state.get('authenticated', False)
    
    def show_auth_required_message(self) -> None:
        """Show message when authentication is required."""
        st.warning(f"Please log in to access {self.page_title}.")
    
    def init_session_state(self, required_keys: Dict[str, Any]) -> None:
        """Initialize required session state keys with default values."""
        for key, default_value in required_keys.items():
            if key not in st.session_state:
                st.session_state[key] = default_value
    
    def show_page_header(self, subtitle: Optional[str] = None) -> None:
        """Show standard page header."""
        st.header(self.page_title)
        if subtitle:
            st.subheader(subtitle)
        st.markdown("---")
    
    def show_error(self, message: str, log_details: Optional[str] = None) -> None:
        """Show error message and optionally log it."""
        st.error(message)
        if log_details:
            get_audit_logger(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="PAGE_ERROR",
                details=f"Page {self.page_name}: {log_details}"
            )
    
    def show_success(self, message: str, log_details: Optional[str] = None) -> None:
        """Show success message and optionally log it."""
        st.success(message)
        if log_details:
            get_audit_logger(
                user=st.session_state.get('username', 'UNKNOWN'),
                role=st.session_state.get('role', 'N/A'),
                action="PAGE_SUCCESS",
                details=f"Page {self.page_name}: {log_details}"
            )
    
    def show_info(self, message: str) -> None:
        """Show info message."""
        st.info(message)
    
    def show_warning(self, message: str) -> None:
        """Show warning message."""
        st.warning(message) 