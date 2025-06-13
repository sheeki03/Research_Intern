"""
MCP Custom Exception Classes

Defines specific exceptions for MCP operations and error handling.
"""

class MCPBaseException(Exception):
    """Base exception for all MCP-related errors."""
    pass

class MCPConnectionError(MCPBaseException):
    """Raised when MCP server connection fails."""
    
    def __init__(self, message: str, server_url: str = None):
        self.server_url = server_url
        super().__init__(message)

class MCPTimeoutError(MCPBaseException):
    """Raised when MCP operation times out."""
    
    def __init__(self, message: str, timeout_duration: float = None):
        self.timeout_duration = timeout_duration
        super().__init__(message)

class MCPRateLimitError(MCPBaseException):
    """Raised when MCP server rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message)

class MCPAuthenticationError(MCPBaseException):
    """Raised when MCP server authentication fails."""
    pass

class MCPToolNotFoundError(MCPBaseException):
    """Raised when requested MCP tool is not available."""
    
    def __init__(self, message: str, tool_name: str = None):
        self.tool_name = tool_name
        super().__init__(message)

class MCPInvalidResponseError(MCPBaseException):
    """Raised when MCP server returns invalid response."""
    
    def __init__(self, message: str, response_data: dict = None):
        self.response_data = response_data
        super().__init__(message) 