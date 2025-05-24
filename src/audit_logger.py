import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socket

_LOGGER_NAME = "audit"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOGS_DIR     = (_PROJECT_ROOT / "logs").expanduser()
_FALLBACK_DIR = Path("/tmp") / "logs"
_LOG_FILE     = _LOGS_DIR / "audit.log"

# --------------------------------------------------------------------------- #
# 1.  Create the directory (or gracefully fall back).                         #
# --------------------------------------------------------------------------- #
try:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_FILE.parent.touch(exist_ok=True)  # ensure we can touch inside folder
except PermissionError:
    _LOGS_DIR = _FALLBACK_DIR # Update the directory path if fallback is used
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = _LOGS_DIR / "audit.log" # Update the log file path

# --------------------------------------------------------------------------- #
# 2.  Build the base logger once.                                             #
# --------------------------------------------------------------------------- #
_logger = logging.getLogger(_LOGGER_NAME)
_logger.setLevel(logging.INFO)
_logger.propagate = False                        # never bubble to root

# ---- A. Temporary handler for setup diagnostics --------------------------- #
_setup_handler = logging.StreamHandler()
_setup_handler.setFormatter(
    logging.Formatter("%(asctime)s | SETUP | %(levelname)s | %(message)s")
)
_logger.addHandler(_setup_handler)

_logger.info("Initialising audit logger …")
_logger.info("Writing audit file to %s", _LOG_FILE)

# ---- B. Production handlers (added only *after* diagnostics succeed) ------ #
_audit_fmt = logging.Formatter(
    # Added ACTION, MODEL, LINKS, DETAILS back as they were in the original formatter and log_audit_event function
    # Kept host as it's useful context provided by the new pattern
    "%(asctime)s | USER: %(user)s | ROLE: %(role)s | HOST: %(host)s | ACTION: %(action)s | MODEL: %(model)s | LINKS: %(links)s | DETAILS: %(details)s" 
)

class RequireAuditFields(logging.Filter):
    """Only pass records that carry the mandatory audit extras."""
    # Adjusted required fields based on the modified formatter
    _needed = {"user", "role", "host", "action", "model", "links", "details"}
    def filter(self, record):
        # Check if all needed keys exist in the record's dictionary
        # Also handle the case where a field might be required but not explicitly passed in extra (like standard 'message'/'msg')
        # The core check is whether the custom fields are present.
        record_dict = record.__dict__
        return self._needed.issubset(record_dict)

try:
    _file_handler = RotatingFileHandler(
        _LOG_FILE, backupCount=3, maxBytes=5_000_000, encoding="utf-8"
    )
    _file_handler.setFormatter(_audit_fmt)
    _file_handler.addFilter(RequireAuditFields())

    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(_audit_fmt)
    _console_handler.addFilter(RequireAuditFields())

    # Swap handlers atomically: remove the temp one, add the real ones
    _logger.handlers.clear()
    _logger.addHandler(_file_handler)
    _logger.addHandler(_console_handler)

    # Log that everything is ready (now we *must* supply the extras)
    # Adding the extra fields needed by the updated formatter
    _logger.info(
        "Audit logger ready",
        extra={
            "user": "SYSTEM", 
            "role": "SYSTEM", 
            "host": socket.gethostname(),
            "action": "INIT",
            "model": "N/A",
            "links": "N/A",
            "details": "Audit logger successfully initialized." # Use 'details' for the main message part too
        }
    )

except Exception as exc:
    # keep the setup handler so at least something is visible
    _logger.error("Failed to prepare production audit handlers: %s", exc, exc_info=True)

# --------------------------------------------------------------------------- #
# 3. Helper to obtain an adapter that always injects the mandatory fields.    #
#    Modified to accept all fields required by the audit formatter.           #
# --------------------------------------------------------------------------- #
def get_audit_logger(
    *, 
    user: str, 
    role: str, 
    action: str,
    details: str, # Added back details
    links: list[str] | None = None,
    model: str | None = None, # Renamed model_name to model for consistency
    host: str | None = None
):
    """Return a LoggerAdapter carrying the mandatory audit fields."""
    processed_links = ", ".join(links) if links and isinstance(links, list) else "N/A"
    model_for_log = model if model else "N/A"
    
    # The 'details' parameter content will become the main message part of the log record.
    # All fields are passed in the 'extra' dictionary for the formatter.
    extra_data = {
        "user": user if user else "SYSTEM",
        "role": role if role else "N/A",
        "host": host or socket.gethostname(),
        "action": action,
        "model": model_for_log,
        "links": processed_links,
        "details": details # Pass details again for the custom formatter field
    }
    
    # Note: The main message passed to adapter.info() etc. is effectively the 'details' field here.
    # We create an adapter but won't directly use its .info(), .error() etc. methods in the typical adapter pattern.
    # Instead, we use the base logger's methods with the prepared extra dict. This ensures the filter passes.
    # This deviates slightly from typical adapter usage but fits the need to pass the full 'extra' dict.
    # The adapter is mainly used here as a convenient way to bundle the extra data conceptually,
    # but we call _logger.info directly with the extra data.

    # Define a logging function that uses the base logger with the extra data
    def log_info_with_extras(message: str):
        # Ensure the message argument aligns with the 'details' field for consistency
        extra_data["details"] = message 
        _logger.info(message, extra=extra_data)

    # We can return the function itself or structure this differently if preferred.
    # For simplicity matching the previous log_audit_event structure, we'll just call _logger.info directly here.
    # This function effectively replaces the old log_audit_event.
    _logger.info(details, extra=extra_data)


# Define the path constant for external use (e.g., in the admin panel)
AUDIT_LOG_FILE_PATH = _LOG_FILE

# Example usage (replaces old __main__ block)
if __name__ == "__main__":
    print(f"Attempting to log to: {AUDIT_LOG_FILE_PATH}")
    # Use the new function, mirroring the old log_audit_event signature
    get_audit_logger(user="test_user", role="admin", action="TEST_ACTION", details="This is a test log event.")
    get_audit_logger(user="another_user", role="researcher", action="ANOTHER_TEST", details="Another test detail.")
    get_audit_logger(
        user="link_submitter", 
        role="researcher", 
        action="LINKS_SUBMITTED", 
        details="User provided web links for research.", 
        links=["http://example.com", "https://anotherexample.org"]
    )
    get_audit_logger(
        user="no_link_user", 
        role="editor", 
        action="CONTENT_EDIT", 
        details="User edited content without providing links."
    )
    print(f"Check the log file: {AUDIT_LOG_FILE_PATH}")
    # Verify file content if possible
    if AUDIT_LOG_FILE_PATH.exists():
        print("\\n--- Log File Content ---")
        print(AUDIT_LOG_FILE_PATH.read_text())
        print("--- End Log File Content ---")
    else:
        print("Log file does not exist.") 