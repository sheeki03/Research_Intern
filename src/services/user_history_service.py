import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
from src.models.chat_models import UserHistoryEntry, ChatSession
from src.config import LOGS_DIR

class UserHistoryService:
    """Service for managing user history with JSON file storage."""
    
    def __init__(self):
        self.history_file = LOGS_DIR / "user_history.json"
        self.ensure_file_exists()
    
    def ensure_file_exists(self):
        """Ensure the history file exists."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_file.exists():
            with open(self.history_file, 'w') as f:
                json.dump([], f)
    
    def load_history(self) -> List[Dict]:
        """Load all history from the JSON file."""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def save_history(self, history: List[Dict]):
        """Save history to the JSON file."""
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=2, default=str)
    
    def add_activity(self, entry: UserHistoryEntry):
        """Add a new activity to the user history."""
        history = self.load_history()
        
        # Convert to dict for JSON storage
        entry_dict = entry.model_dump()
        entry_dict['timestamp'] = entry.timestamp.isoformat()
        
        history.append(entry_dict)
        self.save_history(history)
    
    def cleanup_old_entries(self, hours: int = 48):
        """Remove entries older than specified hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        history = self.load_history()
        
        # Filter out old entries
        filtered_history = []
        for entry in history:
            try:
                entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                if entry_time > cutoff_time:
                    filtered_history.append(entry)
            except (ValueError, KeyError):
                # Keep entries with invalid timestamps for manual review
                filtered_history.append(entry)
        
        self.save_history(filtered_history)
        return len(history) - len(filtered_history)  # Return number of cleaned entries
    
    def get_user_history(self, username: str, hours: int = 48) -> List[UserHistoryEntry]:
        """Get user history for the last N hours."""
        # First cleanup old entries
        self.cleanup_old_entries(hours)
        
        history = self.load_history()
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        user_entries = []
        for entry in history:
            if entry.get('username') == username:
                try:
                    entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                    if entry_time > cutoff_time:
                        # Convert back to UserHistoryEntry
                        entry['timestamp'] = entry_time
                        user_entries.append(UserHistoryEntry(**entry))
                except (ValueError, KeyError):
                    continue
        
        # Sort by timestamp (newest first)
        user_entries.sort(key=lambda x: x.timestamp, reverse=True)
        return user_entries
    
    def get_user_chat_sessions(self, username: str, hours: int = 48) -> List[Dict]:
        """Get user's chat sessions from history for the last N hours."""
        user_history = self.get_user_history(username, hours)
        
        # Group by session_id
        sessions = {}
        for entry in user_history:
            # Include both chat_message and report_generated activities to build sessions
            if entry.activity_type in ['chat_message', 'report_generated', 'session_created'] and entry.session_id:
                if entry.session_id not in sessions:
                    sessions[entry.session_id] = {
                        'session_id': entry.session_id,
                        'report_id': entry.report_id,
                        'username': entry.username,
                        'created_at': entry.timestamp,
                        'last_activity': entry.timestamp,
                        'message_count': 0
                    }
                
                # Only count actual chat messages
                if entry.activity_type == 'chat_message':
                    sessions[entry.session_id]['message_count'] += 1
                
                # Update activity timestamps
                if entry.timestamp > sessions[entry.session_id]['last_activity']:
                    sessions[entry.session_id]['last_activity'] = entry.timestamp
                if entry.timestamp < sessions[entry.session_id]['created_at']:
                    sessions[entry.session_id]['created_at'] = entry.timestamp
        
        # Convert to list and sort by last activity
        session_list = list(sessions.values())
        session_list.sort(key=lambda x: x['last_activity'], reverse=True)
        return session_list
    
    def log_chat_message(self, username: str, session_id: str, report_id: str, 
                        query: str, response: str):
        """Convenience method to log a chat message activity."""
        entry = UserHistoryEntry(
            username=username,
            activity_type='chat_message',
            session_id=session_id,
            report_id=report_id,
            details={
                'query': query,
                'response_length': len(response),
                'query_length': len(query)
            }
        )
        self.add_activity(entry)
    
    def log_session_created(self, username: str, session_id: str, report_id: str):
        """Convenience method to log session creation."""
        entry = UserHistoryEntry(
            username=username,
            activity_type='session_created',
            session_id=session_id,
            report_id=report_id,
            details={'action': 'new_session_created'}
        )
        self.add_activity(entry)

# Global instance
user_history_service = UserHistoryService() 