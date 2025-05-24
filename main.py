"""
AI Research Agent - Main Entry Point
Clean, simple entry point using OOP architecture.
"""

import asyncio
from src.controllers.app_controller import AppController

async def main():
    """Main application entry point."""
    app = AppController()
    await app.run()

if __name__ == "__main__":
    asyncio.run(main()) 