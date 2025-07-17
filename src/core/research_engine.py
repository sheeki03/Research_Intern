"""
Research Engine Abstraction Layer
Provides unified interface for different research backends (Classic vs ODR).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
import asyncio
import time
from pathlib import Path


class ResearchMode(Enum):
    """Available research modes."""
    CLASSIC = "classic"
    DEEP_RESEARCH = "deep_research"  # ODR-based


@dataclass
class ResearchSource:
    """Represents a research source (document, URL, etc.)."""
    content: str
    source_type: str  # "document", "web", "docsend", etc.
    metadata: Dict[str, Any]
    url: Optional[str] = None
    title: Optional[str] = None


@dataclass
class ResearchResult:
    """Result from research engine."""
    content: str
    sources: List[ResearchSource]
    citations: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    processing_time: float
    success: bool
    error_message: Optional[str] = None


class ResearchEngine(ABC):
    """Abstract base class for research engines."""
    
    @abstractmethod
    async def generate_report(
        self,
        query: str,
        sources: List[ResearchSource],
        config: Optional[Dict[str, Any]] = None
    ) -> ResearchResult:
        """Generate research report from query and sources."""
        pass
    
    @abstractmethod
    def get_engine_name(self) -> str:
        """Get engine name for display."""
        pass
    
    @abstractmethod
    def get_engine_description(self) -> str:
        """Get engine description for UI."""
        pass


class ClassicResearchEngine(ResearchEngine):
    """Classic research engine using existing OpenRouter-based pipeline."""
    
    def __init__(self, openrouter_client, model_name: str = None):
        self.openrouter_client = openrouter_client
        self.model_name = model_name or "openai/gpt-4o"
    
    async def generate_report(
        self,
        query: str,
        sources: List[ResearchSource],
        config: Optional[Dict[str, Any]] = None
    ) -> ResearchResult:
        """Generate report using classic pipeline."""
        start_time = time.time()
        
        try:
            # Build prompt from sources
            prompt = self._build_prompt(query, sources)
            
            # Generate response using OpenRouter
            response = await self.openrouter_client.generate_response(
                prompt=prompt,
                system_prompt=config.get("system_prompt", "You are a helpful research assistant."),
                model_override=self.model_name
            )
            
            processing_time = time.time() - start_time
            
            return ResearchResult(
                content=response or "",
                sources=sources,
                citations=self._extract_citations(sources),
                metadata={
                    "engine": "classic",
                    "model": self.model_name,
                    "prompt_length": len(prompt),
                    "source_count": len(sources)
                },
                processing_time=processing_time,
                success=bool(response),
                error_message=None if response else "Empty response from AI"
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            return ResearchResult(
                content="",
                sources=sources,
                citations=[],
                metadata={"engine": "classic", "error": str(e)},
                processing_time=processing_time,
                success=False,
                error_message=str(e)
            )
    
    def _build_prompt(self, query: str, sources: List[ResearchSource]) -> str:
        """Build prompt from query and sources."""
        if query:
            prompt = f"Research Query: {query}\n\n"
        else:
            prompt = "Please generate a comprehensive report based on the provided content.\n\n"
        
        for source in sources:
            if source.source_type == "document":
                prompt += f"Document Content:\n--- Document: {source.metadata.get('name', 'Unknown')} ---\n{source.content}\n\n"
            elif source.source_type == "web":
                prompt += f"Web Content:\n--- URL: {source.url or 'Unknown'} ---\n{source.content}\n\n"
            elif source.source_type == "docsend":
                slides_info = source.metadata.get('slides_processed', 0)
                total_slides = source.metadata.get('total_slides', 0)
                prompt += f"DocSend Presentation Content:\n--- DocSend Deck: {source.url or 'Unknown'} ({slides_info}/{total_slides} slides processed) ---\n{source.content}\n\n"
        
        prompt += "Based on the above content, please generate a comprehensive research report."
        return prompt
    
    def _extract_citations(self, sources: List[ResearchSource]) -> List[Dict[str, Any]]:
        """Extract citations from sources."""
        citations = []
        for i, source in enumerate(sources):
            citation = {
                "id": i + 1,
                "type": source.source_type,
                "title": source.title or source.metadata.get('name', f"Source {i + 1}"),
                "url": source.url,
                "metadata": source.metadata
            }
            citations.append(citation)
        return citations
    
    def get_engine_name(self) -> str:
        return "Classic Research"
    
    def get_engine_description(self) -> str:
        return "Traditional research using direct AI analysis of provided sources"


class DeepResearchEngine(ResearchEngine):
    """Deep research engine using Open Deep Research (ODR) framework."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._odr_available = None
    
    async def _check_odr_availability(self) -> bool:
        """Check if ODR dependencies are available."""
        if self._odr_available is not None:
            return self._odr_available
        
        try:
            # Try importing ODR dependencies
            import sys
            from pathlib import Path
            
            # Add ODR to path
            odr_path = Path(__file__).parent.parent.parent / "open_deep_research" / "src"
            if odr_path.exists():
                sys.path.append(str(odr_path))
            
            from open_deep_research.deep_researcher import (
                create_research_graph, 
                Configuration
            )
            from langchain.chat_models import init_chat_model
            from langchain_core.messages import HumanMessage
            
            self._odr_available = True
            return True
            
        except ImportError as e:
            print(f"ODR dependencies not available: {e}")
            self._odr_available = False
            return False
    
    async def generate_report(
        self,
        query: str,
        sources: List[ResearchSource],
        config: Optional[Dict[str, Any]] = None
    ) -> ResearchResult:
        """Generate report using ODR framework."""
        start_time = time.time()
        
        # Check ODR availability
        if not await self._check_odr_availability():
            return await self._fallback_to_classic(query, sources, config, start_time)
        
        try:
            # Import ODR components
            import sys
            from pathlib import Path
            from langchain_core.messages import HumanMessage
            from langchain_core.runnables import RunnableConfig
            import os
            
            # Add ODR to path
            odr_path = Path(__file__).parent.parent.parent / "open_deep_research" / "src"
            sys.path.append(str(odr_path))
            
            from open_deep_research.deep_researcher import create_research_graph
            from open_deep_research.configuration import Configuration, SearchAPI
            
            # Configure ODR
            odr_config = Configuration(
                search_api=SearchAPI.TAVILY,  # Use Tavily as it works with all models
                max_concurrent_research_units=config.get("concurrency", 3),
                max_researcher_iterations=config.get("depth", 2),
                research_model=self._get_model_name(config),
                research_model_max_tokens=4000,
                compression_model=self._get_model_name(config),
                compression_model_max_tokens=4000,
                final_report_model=self._get_model_name(config),
                final_report_model_max_tokens=8000,
                allow_clarification=False  # Skip clarification for automation
            )
            
            # Create research graph
            graph = create_research_graph()
            
            # Prepare input - combine query with source context
            research_input = self._prepare_odr_input(query, sources)
            
            # Configure environment
            runnable_config = RunnableConfig(
                configurable={
                    "configuration": odr_config,
                    "search_api": SearchAPI.TAVILY.value,
                    "research_model": odr_config.research_model,
                    "compression_model": odr_config.compression_model,
                    "final_report_model": odr_config.final_report_model
                }
            )
            
            # Set API keys
            self._set_api_keys()
            
            # Run ODR research
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=research_input)]},
                config=runnable_config
            )
            
            processing_time = time.time() - start_time
            
            # Extract content from ODR result
            content = self._extract_content_from_odr_result(result)
            citations = self._extract_citations_from_odr_result(result, sources)
            
            return ResearchResult(
                content=content,
                sources=sources,
                citations=citations,
                metadata={
                    "engine": "deep_research",
                    "model": odr_config.research_model,
                    "odr_config": odr_config.dict(),
                    "source_count": len(sources)
                },
                processing_time=processing_time,
                success=bool(content),
                error_message=None if content else "No content generated"
            )
            
        except Exception as e:
            print(f"ODR execution failed: {e}")
            return await self._fallback_to_classic(query, sources, config, start_time)
    
    def _get_model_name(self, config: Optional[Dict[str, Any]]) -> str:
        """Get model name for ODR."""
        if config and config.get("model"):
            return config["model"]
        
        # Check for OpenRouter configuration
        import os
        if os.getenv("OPENROUTER_API_KEY"):
            return "openrouter:openai/gpt-4o"
        return "openai:gpt-4o"
    
    def _set_api_keys(self):
        """Set required API keys for ODR."""
        import os
        
        # Set Tavily API key if available
        if not os.getenv("TAVILY_API_KEY"):
            # Use a placeholder or skip Tavily
            pass
        
        # Ensure OpenAI/OpenRouter key is available
        if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
    
    def _prepare_odr_input(self, query: str, sources: List[ResearchSource]) -> str:
        """Prepare input for ODR that includes source context."""
        input_text = query or "Generate a comprehensive research report"
        
        if sources:
            input_text += "\n\nAdditional Context Sources:\n"
            for source in sources:
                if source.source_type == "document":
                    input_text += f"- Document: {source.metadata.get('name', 'Unknown')}\n"
                elif source.source_type == "web":
                    input_text += f"- Web Source: {source.url or 'Unknown URL'}\n"
                elif source.source_type == "docsend":
                    input_text += f"- DocSend Presentation: {source.url or 'Unknown'}\n"
            
            input_text += "\nPlease incorporate insights from these sources along with additional web research."
        
        return input_text
    
    def _extract_content_from_odr_result(self, result: Dict[str, Any]) -> str:
        """Extract main content from ODR result."""
        # ODR typically returns content in messages or final_report
        if "messages" in result and result["messages"]:
            last_message = result["messages"][-1]
            if hasattr(last_message, 'content'):
                return last_message.content
            elif isinstance(last_message, dict) and 'content' in last_message:
                return last_message['content']
        
        # Fallback to other possible keys
        for key in ["final_report", "report", "content", "research_brief"]:
            if key in result and result[key]:
                return str(result[key])
        
        return ""
    
    def _extract_citations_from_odr_result(self, result: Dict[str, Any], original_sources: List[ResearchSource]) -> List[Dict[str, Any]]:
        """Extract citations from ODR result."""
        citations = []
        
        # Add original sources as citations
        for i, source in enumerate(original_sources):
            citation = {
                "id": i + 1,
                "type": source.source_type,
                "title": source.title or source.metadata.get('name', f"Source {i + 1}"),
                "url": source.url,
                "metadata": source.metadata
            }
            citations.append(citation)
        
        # TODO: Extract additional citations from ODR research results
        # This would require parsing the ODR result for discovered sources
        
        return citations
    
    async def _fallback_to_classic(self, query: str, sources: List[ResearchSource], config: Optional[Dict[str, Any]], start_time: float) -> ResearchResult:
        """Fallback to classic engine if ODR fails."""
        processing_time = time.time() - start_time
        return ResearchResult(
            content="",
            sources=sources,
            citations=[],
            metadata={"engine": "deep_research", "fallback": "odr_unavailable"},
            processing_time=processing_time,
            success=False,
            error_message="Deep Research engine unavailable, please use Classic mode"
        )
    
    def get_engine_name(self) -> str:
        return "Deep Research (ODR)"
    
    def get_engine_description(self) -> str:
        return "Advanced multi-agent research using LangChain's Open Deep Research framework"


class ResearchEngineFactory:
    """Factory for creating research engines."""
    
    @staticmethod
    def create_engine(
        mode: ResearchMode,
        openrouter_client=None,
        config: Optional[Dict[str, Any]] = None
    ) -> ResearchEngine:
        """Create research engine based on mode."""
        if mode == ResearchMode.CLASSIC:
            if not openrouter_client:
                raise ValueError("OpenRouter client required for Classic mode")
            return ClassicResearchEngine(openrouter_client, config.get("model") if config else None)
        
        elif mode == ResearchMode.DEEP_RESEARCH:
            return DeepResearchEngine(config)
        
        else:
            raise ValueError(f"Unknown research mode: {mode}")
    
    @staticmethod
    def get_available_modes() -> List[ResearchMode]:
        """Get list of available research modes."""
        return [ResearchMode.CLASSIC, ResearchMode.DEEP_RESEARCH]
    
    @staticmethod
    def get_mode_descriptions() -> Dict[ResearchMode, str]:
        """Get descriptions for each mode."""
        return {
            ResearchMode.CLASSIC: "Traditional research using direct AI analysis",
            ResearchMode.DEEP_RESEARCH: "Advanced multi-agent research with web search and citations"
        }