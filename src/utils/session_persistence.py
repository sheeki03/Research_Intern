"""
Session persistence utility for maintaining authentication state across page reloads.
Uses browser localStorage to store encrypted session data.
"""

import streamlit as st
import json
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
import os

class SessionPersistence:
    """Handles session persistence using browser localStorage."""
    
    def __init__(self):
        # Generate a key based on environment or use a default
        # In production, this should be a proper secret key
        secret_key = os.getenv('SESSION_SECRET_KEY', 'default-session-key-change-in-production')
        key = hashlib.sha256(secret_key.encode()).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(key))
        self.session_timeout_hours = 24  # Sessions expire after 24 hours
    
    def save_session(self, username: str, role: str, system_prompt: str) -> None:
        """Save session data to browser localStorage."""
        try:
            session_data = {
                'username': username,
                'role': role,
                'system_prompt': system_prompt,
                'timestamp': datetime.utcnow().isoformat(),
                'expires_at': (datetime.utcnow() + timedelta(hours=self.session_timeout_hours)).isoformat()
            }
            
            # Encrypt the session data
            encrypted_data = self._encrypt_data(session_data)
            
            # Save to localStorage using HTML/JavaScript
            html_code = f"""
            <script>
                localStorage.setItem('ai_research_session', '{encrypted_data}');
                console.log('Session saved to localStorage');
            </script>
            """
            st.components.v1.html(html_code, height=0)
            
        except Exception as e:
            print(f"Error saving session: {e}")
    
    def load_session(self) -> Optional[Dict[str, Any]]:
        """Load session data from browser localStorage."""
        try:
            # Create a unique key for this load attempt
            load_key = f"session_load_{datetime.now().timestamp()}"
            
            # JavaScript to retrieve session data and store in Streamlit
            html_code = f"""
            <script>
                const sessionData = localStorage.getItem('ai_research_session');
                if (sessionData) {{
                    // Store in a temporary element that Streamlit can read
                    const hiddenDiv = document.createElement('div');
                    hiddenDiv.id = 'session-data-{load_key}';
                    hiddenDiv.style.display = 'none';
                    hiddenDiv.textContent = sessionData;
                    document.body.appendChild(hiddenDiv);
                    console.log('Session data retrieved from localStorage');
                }} else {{
                    console.log('No session data found in localStorage');
                }}
            </script>
            <div id="session-data-{load_key}" style="display: none;"></div>
            """
            
            # Use session state to track if we've already tried to load
            if f'session_load_attempted_{load_key}' not in st.session_state:
                st.components.v1.html(html_code, height=0)
                st.session_state[f'session_load_attempted_{load_key}'] = True
                return None  # Return None on first attempt, data will be available on next run
            
            # For now, return None as we can't easily read from localStorage in Streamlit
            # We'll use a different approach with query parameters
            return None
            
        except Exception as e:
            print(f"Error loading session: {e}")
            return None
    
    def clear_session(self) -> None:
        """Clear session data from browser localStorage."""
        try:
            html_code = """
            <script>
                localStorage.removeItem('ai_research_session');
                console.log('Session cleared from localStorage');
            </script>
            """
            st.components.v1.html(html_code, height=0)
            
        except Exception as e:
            print(f"Error clearing session: {e}")
    
    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        """Encrypt session data."""
        try:
            json_data = json.dumps(data)
            encrypted_bytes = self.cipher.encrypt(json_data.encode())
            return base64.urlsafe_b64encode(encrypted_bytes).decode()
        except Exception as e:
            print(f"Error encrypting data: {e}")
            return ""
    
    def _decrypt_data(self, encrypted_data: str) -> Optional[Dict[str, Any]]:
        """Decrypt session data."""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return json.loads(decrypted_bytes.decode())
        except Exception as e:
            print(f"Error decrypting data: {e}")
            return None
    
    def is_session_valid(self, session_data: Dict[str, Any]) -> bool:
        """Check if session data is still valid (not expired)."""
        try:
            expires_at = datetime.fromisoformat(session_data.get('expires_at', ''))
            return datetime.utcnow() < expires_at
        except Exception:
            return False

# Alternative approach using URL parameters for session persistence
class URLSessionPersistence:
    """Simpler session persistence using URL parameters."""
    
    def __init__(self):
        self.session_timeout_hours = 24
    
    def _create_session_token(self, username: str, role: str) -> str:
        """Create a session token for URL persistence."""
        # Use a separator that won't appear in the timestamp
        timestamp = datetime.utcnow().isoformat().replace(':', '_')  # Replace colons with underscores
        return base64.urlsafe_b64encode(f"{username}|{role}|{timestamp}".encode()).decode()
    
    def save_session_to_url(self, username: str, role: str) -> None:
        """Save session info to URL parameters (for demo purposes)."""
        try:
            # Create a session token using the same format as _create_session_token
            session_token = self._create_session_token(username, role)
            
            # Show instructions to user
            st.info(f"""
            **Session Persistence Enabled**
            
            To maintain your session across page reloads, bookmark this URL with the session token:
            `?session={session_token}`
            
            Your session will remain active for 24 hours.
            """)
            
        except Exception as e:
            print(f"Error creating session URL: {e}")
    
    def load_session_from_url(self) -> Optional[Dict[str, Any]]:
        """Load session from URL parameters."""
        try:
            query_params = st.query_params
            session_token = query_params.get('session', None)
            
            if not session_token:
                return None
            
            # Decode session token
            decoded = base64.urlsafe_b64decode(session_token.encode()).decode()
            parts = decoded.split('|')  # Use pipe separator instead of colon
            
            if len(parts) == 3:  # Expect exactly 3 parts
                username = parts[0]
                role = parts[1]
                timestamp_str = parts[2].replace('_', ':')  # Convert underscores back to colons
                
                # Check if session is still valid
                timestamp = datetime.fromisoformat(timestamp_str)
                time_diff = datetime.utcnow() - timestamp
                
                if time_diff < timedelta(hours=self.session_timeout_hours):
                    return {
                        'username': username,
                        'role': role,
                        'timestamp': timestamp_str
                    }
            
            return None
            
        except Exception as e:
            print(f"Error loading session from URL: {e}")
            return None

# Global instances
session_persistence = SessionPersistence()
url_session_persistence = URLSessionPersistence() 