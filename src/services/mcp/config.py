"""
MCP Configuration Management Module

Handles loading and validation of MCP server configurations.
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class MCPConfig:
    """MCP Configuration manager for loading and validating MCP server settings."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize MCP configuration.
        
        Args:
            config_path: Path to MCP config file. Defaults to config/mcp_config.json
        """
        if config_path is None:
            # Try multiple potential locations for the config file
            potential_paths = [
                # First try environment variable if set
                os.environ.get('MCP_CONFIG_PATH'),
                # Docker container path
                '/app/config/mcp_config.json',
                # Local development path (relative to project root)
                Path(__file__).parent.parent.parent.parent / "config" / "mcp_config.json",
                # Alternative relative path
                './config/mcp_config.json',
                # Current directory
                'mcp_config.json'
            ]
            
            config_path = None
            for path in potential_paths:
                if path and Path(path).exists():
                    config_path = path
                    break
            
            if config_path is None:
                # If no config found, default to the expected Docker location
                config_path = '/app/config/mcp_config.json'
        
        self.config_path = Path(config_path)
        self._config: Optional[Dict[str, Any]] = None
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from JSON file."""
        try:
            if not self.config_path.exists():
                logger.warning(f"MCP config file not found: {self.config_path}")
                logger.info("Creating default MCP configuration...")
                self._create_default_config()
                return
            
            with open(self.config_path, 'r') as f:
                self._config = json.load(f)
            
            self._validate_config()
            logger.info(f"MCP configuration loaded from {self.config_path}")
            
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            logger.info("Falling back to default configuration...")
            self._create_default_config()
    
    def _create_default_config(self) -> None:
        """Create a default configuration if none exists."""
        self._config = {
            "mcpServers": {
                "coingecko": {
                    "command": "npx",
                    "args": [
                        "mcp-remote",
                        "https://mcp.api.coingecko.com/sse"
                    ],
                    "timeout": 30,
                    "retryAttempts": 3,
                    "rateLimits": {
                        "requestsPerMinute": 100,
                        "burstSize": 10
                    }
                }
            },
            "fallbackEndpoints": {
                "coingecko_rest": "https://api.coingecko.com/api/v3"
            },
            "connection": {
                "maxRetries": 3,
                "retryDelay": 5,
                "healthCheckInterval": 60,
                "connectionTimeout": 30
            },
            "logging": {
                "level": "INFO",
                "enableDebug": False,
                "logMCPMessages": True
            }
        }
        
        # Try to create the config directory and file
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Default MCP configuration created at {self.config_path}")
        except Exception as e:
            logger.warning(f"Could not save default config to {self.config_path}: {e}")
            logger.info("Using in-memory default configuration")
        
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate the loaded configuration structure."""
        if not self._config:
            raise ValueError("Configuration is empty")
        
        required_keys = ['mcpServers']
        for key in required_keys:
            if key not in self._config:
                raise ValueError(f"Missing required config key: {key}")
        
        # Validate CoinGecko server config
        coingecko_config = self._config['mcpServers'].get('coingecko')
        if not coingecko_config:
            raise ValueError("CoinGecko MCP server configuration not found")
        
        required_server_keys = ['command', 'args']
        for key in required_server_keys:
            if key not in coingecko_config:
                raise ValueError(f"Missing required CoinGecko config key: {key}")
    
    @property
    def coingecko_config(self) -> Dict[str, Any]:
        """Get CoinGecko MCP server configuration."""
        if not self._config:
            raise ValueError("Configuration not loaded")
        return self._config['mcpServers']['coingecko']
    
    @property
    def fallback_endpoints(self) -> Dict[str, str]:
        """Get fallback REST API endpoints."""
        if not self._config:
            raise ValueError("Configuration not loaded")
        return self._config.get('fallbackEndpoints', {})
    
    @property
    def connection_config(self) -> Dict[str, Any]:
        """Get connection configuration settings."""
        if not self._config:
            raise ValueError("Configuration not loaded")
        return self._config.get('connection', {
            'maxRetries': 3,
            'retryDelay': 5,
            'healthCheckInterval': 60,
            'connectionTimeout': 30
        })
    
    @property
    def logging_config(self) -> Dict[str, Any]:
        """Get logging configuration settings."""
        if not self._config:
            raise ValueError("Configuration not loaded")
        return self._config.get('logging', {
            'level': 'INFO',
            'enableDebug': False,
            'logMCPMessages': True
        })
    
    def get_server_config(self, server_name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            Server configuration dict or None if not found
        """
        if not self._config:
            raise ValueError("Configuration not loaded")
        return self._config['mcpServers'].get(server_name)
    
    def reload_config(self) -> None:
        """Reload configuration from file."""
        self.load_config() 