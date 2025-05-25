"""
Enhanced Audit Logger for AI Research Agent.
Tracks all user actions, AI interactions, and system events with detailed context.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import socket

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Define the audit log file path
AUDIT_LOG_PATH = LOGS_DIR / "audit.log"

# Configure audit logger
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)

# Create file handler if not already exists
if not audit_logger.handlers:
    file_handler = logging.FileHandler(AUDIT_LOG_PATH, encoding='utf-8')
    
    # Enhanced formatter with more detailed information
    formatter = logging.Formatter(
        '%(asctime)s | USER: %(user)s | ROLE: %(role)s | HOST: %(hostname)s | ACTION: %(action)s | MODEL: %(model)s | PROMPT_LENGTH: %(prompt_length)s | DETAILS: %(details)s'
    )
    file_handler.setFormatter(formatter)
    audit_logger.addHandler(file_handler)

def get_audit_logger(
    user: str, 
    role: str, 
    action: str, 
    details: str = "",
    model: str = "N/A",
    prompt: str = "",
    response_length: int = 0,
    processing_time: float = 0.0,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Enhanced audit logging function with comprehensive tracking.
    
    Args:
        user: Username performing the action
        role: User's role (admin, researcher, etc.)
        action: Action being performed
        details: Additional details about the action
        model: AI model used (if applicable)
        prompt: AI prompt used (if applicable) - will be truncated for logging
        response_length: Length of AI response (if applicable)
        processing_time: Time taken for processing (if applicable)
        additional_context: Additional context data
    """
    try:
        hostname = socket.gethostname()
    except:
        hostname = "unknown"
    
    # Truncate prompt for logging (keep first 200 chars)
    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
    prompt_length = len(prompt) if prompt else 0
    
    # Build enhanced details
    enhanced_details = details
    if prompt:
        enhanced_details += f" | PROMPT_PREVIEW: {prompt_preview}"
    if response_length > 0:
        enhanced_details += f" | RESPONSE_LENGTH: {response_length}"
    if processing_time > 0:
        enhanced_details += f" | PROCESSING_TIME: {processing_time:.2f}s"
    if additional_context:
        context_str = " | ".join([f"{k}: {v}" for k, v in additional_context.items()])
        enhanced_details += f" | CONTEXT: {context_str}"
    
    # Log the audit event
    audit_logger.info(
        "",
        extra={
            'user': user,
            'role': role,
            'hostname': hostname,
            'action': action,
            'model': model,
            'prompt_length': prompt_length,
            'details': enhanced_details
        }
    )

def log_ai_interaction(
    user: str,
    role: str,
    model: str,
    prompt: str,
    response: str = "",
    processing_time: float = 0.0,
    page: str = "",
    success: bool = True
) -> None:
    """
    Specialized logging for AI interactions.
    
    Args:
        user: Username
        role: User role
        model: AI model used
        prompt: Full prompt sent to AI
        response: AI response received
        processing_time: Time taken for AI processing
        page: Page where interaction occurred
        success: Whether the interaction was successful
    """
    action = "AI_INTERACTION_SUCCESS" if success else "AI_INTERACTION_FAILED"
    
    additional_context = {
        "page": page,
        "response_length": len(response),
        "prompt_words": len(prompt.split()) if prompt else 0
    }
    
    get_audit_logger(
        user=user,
        role=role,
        action=action,
        details=f"AI interaction on {page}",
        model=model,
        prompt=prompt,
        response_length=len(response),
        processing_time=processing_time,
        additional_context=additional_context
    )

def log_document_processing(
    user: str,
    role: str,
    filename: str,
    file_type: str,
    file_size: int,
    processing_time: float = 0.0,
    success: bool = True,
    extracted_length: int = 0
) -> None:
    """
    Log document processing activities.
    """
    action = "DOCUMENT_PROCESSED" if success else "DOCUMENT_PROCESSING_FAILED"
    
    additional_context = {
        "filename": filename,
        "file_type": file_type,
        "file_size_bytes": file_size,
        "extracted_text_length": extracted_length
    }
    
    get_audit_logger(
        user=user,
        role=role,
        action=action,
        details=f"Processed document: {filename} ({file_type}, {file_size} bytes)",
        processing_time=processing_time,
        additional_context=additional_context
    )

def log_web_scraping(
    user: str,
    role: str,
    urls: list,
    success_count: int,
    failed_count: int,
    processing_time: float = 0.0
) -> None:
    """
    Log web scraping activities.
    """
    action = "WEB_SCRAPING_COMPLETED"
    
    additional_context = {
        "total_urls": len(urls),
        "successful_scrapes": success_count,
        "failed_scrapes": failed_count,
        "success_rate": f"{(success_count / len(urls) * 100):.1f}%" if urls else "0%"
    }
    
    get_audit_logger(
        user=user,
        role=role,
        action=action,
        details=f"Scraped {len(urls)} URLs: {success_count} successful, {failed_count} failed",
        processing_time=processing_time,
        additional_context=additional_context
    )

def log_docsend_processing(
    user: str,
    role: str,
    docsend_url: str,
    slides_processed: int,
    total_slides: int,
    processing_time: float = 0.0,
    success: bool = True,
    extracted_length: int = 0
) -> None:
    """
    Log DocSend processing activities.
    """
    action = "DOCSEND_PROCESSED" if success else "DOCSEND_PROCESSING_FAILED"
    
    additional_context = {
        "docsend_url": docsend_url,
        "slides_processed": slides_processed,
        "total_slides": total_slides,
        "completion_rate": f"{(slides_processed / total_slides * 100):.1f}%" if total_slides > 0 else "0%",
        "extracted_text_length": extracted_length
    }
    
    get_audit_logger(
        user=user,
        role=role,
        action=action,
        details=f"DocSend processing: {slides_processed}/{total_slides} slides from {docsend_url}",
        processing_time=processing_time,
        additional_context=additional_context
    )

def log_notion_activity(
    user: str,
    role: str,
    action_type: str,
    page_count: int = 0,
    processing_time: float = 0.0,
    success: bool = True,
    additional_details: str = ""
) -> None:
    """
    Log Notion-related activities.
    """
    action = f"NOTION_{action_type.upper()}"
    if not success:
        action += "_FAILED"
    
    additional_context = {
        "notion_pages": page_count,
        "operation_type": action_type
    }
    
    details = f"Notion {action_type}"
    if page_count > 0:
        details += f" ({page_count} pages)"
    if additional_details:
        details += f" - {additional_details}"
    
    get_audit_logger(
        user=user,
        role=role,
        action=action,
        details=details,
        processing_time=processing_time,
        additional_context=additional_context
    )

def log_user_action(
    user: str,
    role: str,
    action: str,
    page: str = "",
    details: str = "",
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log general user actions.
    """
    full_details = f"Page: {page}" if page else ""
    if details:
        full_details += f" | {details}" if full_details else details
    
    get_audit_logger(
        user=user,
        role=role,
        action=action,
        details=full_details,
        additional_context=additional_context
    )

def log_admin_action(
    user: str,
    action: str,
    target: str = "",
    details: str = "",
    success: bool = True
) -> None:
    """
    Log administrative actions.
    """
    action_name = f"ADMIN_{action.upper()}"
    if not success:
        action_name += "_FAILED"
    
    full_details = details
    if target:
        full_details = f"Target: {target}" + (f" | {details}" if details else "")
    
    get_audit_logger(
        user=user,
        role="admin",
        action=action_name,
        details=full_details
    )

def log_system_event(
    event_type: str,
    details: str = "",
    severity: str = "INFO"
) -> None:
    """
    Log system-level events.
    """
    action = f"SYSTEM_{event_type.upper()}_{severity}"
    
    get_audit_logger(
        user="SYSTEM",
        role="SYSTEM",
        action=action,
        details=details
    )

def get_activity_summary(hours: int = 24) -> Dict[str, Any]:
    """
    Get activity summary for the specified time period.
    
    Args:
        hours: Number of hours to look back
        
    Returns:
        Dictionary with activity statistics
    """
    try:
        import glob
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        log_files = glob.glob("logs/audit*.log")
        
        stats = {
            "total_actions": 0,
            "unique_users": set(),
            "ai_interactions": 0,
            "document_processing": 0,
            "web_scraping": 0,
            "docsend_processing": 0,
            "notion_activities": 0,
            "admin_actions": 0,
            "failed_actions": 0,
            "models_used": {},
            "pages_accessed": {},
            "hourly_activity": {}
        }
        
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            parts = line.split(' | ')
                            if len(parts) >= 6:
                                try:
                                    timestamp_str = parts[0]
                                    log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
                                    
                                    if log_time > cutoff_time:
                                        stats["total_actions"] += 1
                                        
                                        user = parts[1].replace('USER: ', '')
                                        action = parts[4].replace('ACTION: ', '')
                                        model = parts[5].replace('MODEL: ', '')
                                        
                                        if user != 'SYSTEM':
                                            stats["unique_users"].add(user)
                                        
                                        # Categorize actions
                                        if "AI_INTERACTION" in action:
                                            stats["ai_interactions"] += 1
                                        elif "DOCUMENT" in action:
                                            stats["document_processing"] += 1
                                        elif "WEB_SCRAPING" in action:
                                            stats["web_scraping"] += 1
                                        elif "DOCSEND" in action:
                                            stats["docsend_processing"] += 1
                                        elif "NOTION" in action:
                                            stats["notion_activities"] += 1
                                        elif "ADMIN" in action:
                                            stats["admin_actions"] += 1
                                        
                                        if "FAILED" in action:
                                            stats["failed_actions"] += 1
                                        
                                        # Track models
                                        if model and model != "N/A":
                                            stats["models_used"][model] = stats["models_used"].get(model, 0) + 1
                                        
                                        # Track hourly activity
                                        hour_key = log_time.strftime("%H:00")
                                        stats["hourly_activity"][hour_key] = stats["hourly_activity"].get(hour_key, 0) + 1
                                        
                                except ValueError:
                                    continue
            except Exception:
                continue
        
        # Convert set to count
        stats["unique_users"] = len(stats["unique_users"])
        
        return stats
        
    except Exception:
        return {"error": "Failed to generate activity summary"}

def get_user_activity_details(hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get detailed user activity logs for admin monitoring.
    
    Args:
        hours: Number of hours to look back
        limit: Maximum number of entries to return
        
    Returns:
        List of detailed activity entries
    """
    try:
        import glob
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        log_files = glob.glob("logs/audit*.log")
        
        activities = []
        
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            parts = line.split(' | ')
                            if len(parts) >= 7:
                                try:
                                    timestamp_str = parts[0]
                                    log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
                                    
                                    if log_time > cutoff_time:
                                        user = parts[1].replace('USER: ', '')
                                        role = parts[2].replace('ROLE: ', '')
                                        action = parts[4].replace('ACTION: ', '')
                                        model = parts[5].replace('MODEL: ', '')
                                        prompt_length = parts[6].replace('PROMPT_LENGTH: ', '')
                                        details = parts[7].replace('DETAILS: ', '') if len(parts) > 7 else ""
                                        
                                        # Parse additional details for specific information
                                        parsed_details = _parse_activity_details(details)
                                        
                                        activity = {
                                            "timestamp": log_time,
                                            "user": user,
                                            "role": role,
                                            "action": action,
                                            "model": model if model != "N/A" else None,
                                            "prompt_length": int(prompt_length) if prompt_length.isdigit() else 0,
                                            "details": details,
                                            "parsed_details": parsed_details
                                        }
                                        
                                        activities.append(activity)
                                        
                                except (ValueError, IndexError):
                                    continue
            except Exception:
                continue
        
        # Sort by timestamp (newest first) and limit results
        activities.sort(key=lambda x: x["timestamp"], reverse=True)
        return activities[:limit]
        
    except Exception:
        return []

def _parse_activity_details(details: str) -> Dict[str, Any]:
    """
    Parse activity details to extract specific information.
    
    Args:
        details: Raw details string from log
        
    Returns:
        Dictionary with parsed information
    """
    parsed = {}
    
    try:
        # Extract URLs from web scraping activities
        if "URLs:" in details:
            urls_section = details.split("URLs:")[1].split("|")[0].strip()
            parsed["urls"] = urls_section
        
        # Extract model information
        if "Selected AI model:" in details:
            model_section = details.split("Selected AI model:")[1].split("|")[0].strip()
            parsed["selected_model"] = model_section
        
        # Extract research query
        if "Research query entered:" in details:
            query_section = details.split("Research query entered:")[1].split("|")[0].strip()
            parsed["research_query"] = query_section
        
        # Extract prompt preview
        if "PROMPT_PREVIEW:" in details:
            prompt_section = details.split("PROMPT_PREVIEW:")[1].split("|")[0].strip()
            parsed["prompt_preview"] = prompt_section
        
        # Extract processing time
        if "PROCESSING_TIME:" in details:
            time_section = details.split("PROCESSING_TIME:")[1].split("|")[0].strip()
            parsed["processing_time"] = time_section
        
        # Extract response length
        if "RESPONSE_LENGTH:" in details:
            length_section = details.split("RESPONSE_LENGTH:")[1].split("|")[0].strip()
            parsed["response_length"] = length_section
        
        # Extract page information
        if "Page:" in details:
            page_section = details.split("Page:")[1].split("|")[0].strip()
            parsed["page"] = page_section
        
        # Extract DocSend information
        if "DocSend" in details:
            parsed["involves_docsend"] = True
            if "slides processed:" in details:
                slides_section = details.split("slides processed:")[1].split("|")[0].strip()
                parsed["docsend_slides"] = slides_section
        
        # Extract sitemap information
        if "sitemap" in details.lower():
            parsed["involves_sitemap"] = True
            if "URLs found" in details:
                found_section = details.split("URLs found")[0].split(":")[-1].strip()
                parsed["sitemap_urls_found"] = found_section
        
        # Extract file information
        if "document" in details.lower() or "file" in details.lower():
            parsed["involves_documents"] = True
        
    except Exception:
        pass
    
    return parsed

# Initialize audit logger on import
try:
    log_system_event("AUDIT_LOGGER_INITIALIZED", "Enhanced audit logging system started successfully")
except Exception as e:
    print(f"Warning: Failed to initialize audit logger: {e}")

# Define the path constant for external use (e.g., in the admin panel)
AUDIT_LOG_FILE_PATH = str(AUDIT_LOG_PATH)

# Example usage for testing
if __name__ == "__main__":
    # Test the enhanced audit logger
    log_system_event("TEST_EVENT", "Testing enhanced audit logger functionality")
    
    log_ai_interaction(
        user="test_user",
        role="admin",
        model="gpt-4",
        prompt="What is the capital of France?",
        response="The capital of France is Paris.",
        processing_time=1.5,
        page="Interactive Research",
        success=True
    )
    
    print("Enhanced audit logger test completed. Check logs/audit.log for entries.") 