"""
Open Deep Research (ODR) Service Module

This module encapsulates all ODR integration logic, including:
- Input adaptation from various sources to ODR format
- ODR client initialization and execution
- Output mapping and citation extraction
- Error handling and fallback logic
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ODRSource:
    """Represents a source for ODR processing."""
    content: str
    source_type: str  # "document", "web", "docsend"
    metadata: Dict[str, Any]
    url: Optional[str] = None
    title: Optional[str] = None


@dataclass
class ODRResult:
    """Result from ODR processing."""
    content: str
    sources_used: List[ODRSource]
    citations: List[Dict[str, Any]]
    research_metadata: Dict[str, Any]
    processing_time: float
    success: bool
    error_message: Optional[str] = None
    fallback_used: bool = False
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class ODRService:
    """Service for Open Deep Research integration."""
    
    def __init__(self):
        self._odr_available = None
        self._graph = None
        self._last_error = None
        
    async def is_available(self) -> bool:
        """Check if ODR is available and properly configured."""
        if self._odr_available is not None:
            return self._odr_available
            
        try:
            # Check ODR dependencies
            await self._check_dependencies()
            
            # Check API keys
            self._check_api_keys()
            
            # Initialize ODR graph
            await self._initialize_odr()
            
            self._odr_available = True
            logger.info("ODR service initialized successfully")
            return True
            
        except Exception as e:
            self._last_error = str(e)
            self._odr_available = False
            logger.error(f"ODR service initialization failed: {e}")
            return False
    
    async def generate_report(
        self,
        query: str,
        sources: List[ODRSource],
        config: Optional[Dict[str, Any]] = None
    ) -> ODRResult:
        """
        Generate research report using ODR.
        
        Args:
            query: Research question/topic
            sources: List of sources to incorporate
            config: Optional configuration (breadth, depth, model, etc.)
            
        Returns:
            ODRResult with generated content and metadata
        """
        start_time = time.time()
        
        # Check availability
        if not await self.is_available():
            return ODRResult(
                content="",
                sources_used=sources,
                citations=[],
                research_metadata={"error": self._last_error},
                processing_time=time.time() - start_time,
                success=False,
                error_message=f"ODR not available: {self._last_error}",
                fallback_used=False,
                needs_clarification=False,
                clarification_question=None
            )
        
        try:
            logger.info(f"Starting ODR research for query: {query[:100]}...")
            
            # Prepare ODR input
            odr_input = await self._prepare_odr_input(query, sources, config)
            
            # Configure ODR
            odr_config = self._create_odr_config(config or {}, sources)
            
            # Execute ODR research
            result = await self._execute_odr_research(odr_input, odr_config)
            
            # Process ODR output
            content = self._extract_content(result)
            citations = self._extract_citations(result, sources)
            metadata = self._extract_metadata(result, odr_config)
            
            # Check if this is a clarification question
            needs_clarification, clarification_question = self._check_for_clarification(content)
            
            processing_time = time.time() - start_time
            
            logger.info(f"ODR research completed in {processing_time:.2f}s")
            
            return ODRResult(
                content=content,
                sources_used=sources,
                citations=citations,
                research_metadata=metadata,
                processing_time=processing_time,
                success=bool(content) and not needs_clarification,
                error_message=None if content else "No content generated",
                fallback_used=False,
                needs_clarification=needs_clarification,
                clarification_question=clarification_question
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"ODR research failed: {e}")
            
            return ODRResult(
                content="",
                sources_used=sources,
                citations=[],
                research_metadata={"error": str(e)},
                processing_time=processing_time,
                success=False,
                error_message=str(e),
                fallback_used=False,
                needs_clarification=False,
                clarification_question=None
            )
    
    async def continue_research_with_clarification(
        self,
        clarification_response: str,
        original_query: str,
        sources: List[ODRSource],
        config: Optional[Dict[str, Any]] = None
    ) -> ODRResult:
        """Continue research with user's clarification response."""
        try:
            # Combine original query with clarification response
            enhanced_query = f"{original_query}\n\nAdditional Context:\n{clarification_response}"
            
            # Continue with the enhanced query
            return await self.generate_report(enhanced_query, sources, config)
            
        except Exception as e:
            logger.error(f"Failed to continue research with clarification: {e}")
            return ODRResult(
                content="",
                sources_used=sources,
                citations=[],
                research_metadata={"error": str(e)},
                processing_time=0.0,
                success=False,
                error_message=f"Failed to continue research: {e}",
                fallback_used=False,
                needs_clarification=False,
                clarification_question=None
            )
    
    async def _check_dependencies(self) -> None:
        """Check if all ODR dependencies are available."""
        # Add ODR to Python path
        odr_path = Path(__file__).parent.parent.parent / "open_deep_research" / "src"
        if not odr_path.exists():
            raise ImportError("ODR source code not found. Please clone the repository.")
        
        if str(odr_path) not in sys.path:
            sys.path.append(str(odr_path))
        
        # Test critical imports
        try:
            from open_deep_research.deep_researcher import deep_researcher
            from open_deep_research.configuration import Configuration, SearchAPI
            from open_deep_research.state import AgentState
            from langchain.chat_models import init_chat_model
            from langchain_core.messages import HumanMessage
            from langchain_core.runnables import RunnableConfig
        except ImportError as e:
            raise ImportError(f"Missing ODR dependency: {e}")
    
    def _check_api_keys(self) -> None:
        """Check if required API keys are available."""
        # Check for OpenAI/OpenRouter key
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
            raise ValueError("No OpenAI or OpenRouter API key found")
        
        # Set OpenAI key from OpenRouter if needed for ODR compatibility
        if os.getenv("OPENROUTER_API_KEY"):
            # ODR uses LangChain's init_chat_model which expects OPENAI_API_KEY for OpenAI models
            os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
            # Also set the base URL for OpenRouter
            os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
        
        # Tavily is required for web search in ODR
        if not os.getenv("TAVILY_API_KEY"):
            logger.warning("TAVILY_API_KEY not found. ODR will not be able to perform web search - only provided sources will be used.")
            # Note: ODR can still work with just provided sources or fallback search methods
    
    async def _initialize_odr(self) -> None:
        """Initialize ODR graph."""
        try:
            from open_deep_research.deep_researcher import deep_researcher
            
            # Use the compiled research graph
            self._graph = deep_researcher
            
            # Test with a simple invocation to ensure it works
            # (This is a dry run to catch configuration issues early)
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize ODR graph: {e}")
    
    async def _prepare_odr_input(
        self,
        query: str,
        sources: List[ODRSource],
        config: Dict[str, Any]
    ) -> str:
        """
        Prepare input for ODR that incorporates provided sources.
        
        This is the "Input Adapter Layer" that converts our heterogeneous
        sources into a format ODR can work with.
        """
        # Start with enhanced query - provide context and scope
        if query:
            input_text = f"""Please conduct extremely comprehensive and detailed research on: {query}

Research Requirements:
- Generate a COMPREHENSIVE, LENGTHY, and DETAILED report (minimum 2000+ words)
- Provide extensive general overview, technical analysis, and background information
- Include thorough market potential analysis and complete competitive landscape
- Cover ALL recent developments, key milestones, and historical context
- Analyze team backgrounds, all partnerships, community engagement, and governance
- Include detailed financial metrics, tokenomics, funding history, and valuation analysis
- Provide comprehensive risk assessment and opportunity analysis
- Add market comparisons, industry trends, and future outlook
- Include regulatory considerations and compliance status
- Cover technical architecture, security features, and innovation aspects

Format Requirements:
- Use detailed sections with comprehensive subsections
- Include executive summary and conclusion
- Provide extensive citations and sources
- Use bullet points and structured formatting for clarity
- Aim for academic-level depth and professional quality

Please provide the most detailed, thorough, and lengthy analysis possible with extensive citations."""
        else:
            input_text = "Conduct comprehensive research on this topic with detailed analysis"
        
        # If user provided sources, include them as reference material (not mandatory)
        if sources:
            input_text += "\n\nAdditional reference materials provided by user:\n"
            
            # Simplified, non-directive source inclusion
            for i, source in enumerate(sources, 1):
                if source.source_type == "document":
                    name = source.metadata.get('name', f'Document {i}')
                    content = self._truncate_content(source.content, max_chars=3000)
                    input_text += f"\n[Document: {name}]\n{content}\n"
                elif source.source_type == "web":
                    url = source.url or f'Web Source {i}'
                    content = self._truncate_content(source.content, max_chars=2000)
                    input_text += f"\n[Web Source: {url}]\n{content}\n"
                elif source.source_type == "docsend":
                    url = source.url or f'Presentation {i}'
                    content = self._truncate_content(source.content, max_chars=3000)
                    input_text += f"\n[Presentation: {url}]\n{content}\n"
        
        # Keep it simple - let ODR handle the research approach
        
        return input_text
    
    def _create_odr_config(self, config: Dict[str, Any], sources: List[ODRSource] = None) -> Dict[str, Any]:
        """Create ODR configuration from user config."""
        from open_deep_research.configuration import Configuration, SearchAPI
        
        # Always enable full web search capabilities - let ODR do its thing
        search_api = SearchAPI.TAVILY if os.getenv("TAVILY_API_KEY") else SearchAPI.NONE
        max_iterations = config.get("depth", 2)  # Use full depth regardless of user sources
        
        # Default configuration
        odr_config = Configuration(
            # Search configuration
            search_api=search_api,
            
            # Concurrency and iterations (adjusted based on user sources)
            max_concurrent_research_units=config.get("breadth", 3),
            max_researcher_iterations=max_iterations,
            max_react_tool_calls=config.get("max_tool_calls", 5),
            
            # Model configuration
            research_model=self._get_model_name(config),
            research_model_max_tokens=4000,
            compression_model=self._get_model_name(config),
            compression_model_max_tokens=4000,
            final_report_model=self._get_model_name(config),
            final_report_model_max_tokens=8000,
            
            # Behavior
            allow_clarification=True,  # Enable clarification for better research
            max_structured_output_retries=3
        )
        
        return {
            "configuration": odr_config,
            "search_api": odr_config.search_api.value,
            "research_model": odr_config.research_model,
            "compression_model": odr_config.compression_model,
            "final_report_model": odr_config.final_report_model
        }
    
    def _get_model_name(self, config: Dict[str, Any]) -> str:
        """Get appropriate model name for ODR."""
        # Use user-specified model if available
        if config.get("model"):
            model = config["model"]
            
            # Handle different model providers for ODR compatibility
            if model.startswith("openai/"):
                # OpenAI models via OpenRouter - use OpenAI format directly
                return model.replace("openai/", "openai:")
            elif model.startswith("anthropic/"):
                # Anthropic models via OpenRouter - use Anthropic format directly
                return model.replace("anthropic/", "anthropic:")
            elif model.startswith("google/"):
                # Google models via OpenRouter - fallback to OpenAI
                logger.warning(f"Google model {model} not directly supported by ODR, using OpenAI fallback")
                return "openai:gpt-4o"
            elif model.startswith("qwen/") or model.startswith("tngtech/"):
                # Qwen and other OpenRouter-specific models - fallback to OpenAI
                logger.warning(f"OpenRouter model {model} not directly supported by ODR, using OpenAI fallback")
                return "openai:gpt-4o"
            elif model.startswith("dmind/"):
                # Nano-GPT models - fallback to OpenAI
                logger.warning(f"Nano-GPT model {model} not supported by ODR, using OpenAI fallback")
                return "openai:gpt-4o"
            elif "/" in model and not ":" in model:
                # Generic provider/model format - try OpenAI fallback
                logger.warning(f"Unknown model format {model}, using OpenAI fallback")
                return "openai:gpt-4o"
            return model
        
        # Default model selection based on available keys
        if os.getenv("OPENROUTER_API_KEY"):
            return "openai:gpt-4o"  # Use standard OpenAI model via OpenRouter key
        elif os.getenv("OPENAI_API_KEY"):
            return "openai:gpt-4o"
        elif os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic:claude-3-5-sonnet-20241022"
        else:
            return "openai:gpt-4o"  # Default fallback
    
    async def _execute_odr_research(self, input_text: str, odr_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute ODR research with proper async handling."""
        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig
        
        # Prepare messages
        messages = [HumanMessage(content=input_text)]
        
        # Create runnable config
        runnable_config = RunnableConfig(configurable=odr_config)
        
        # Execute research
        # ODR's graph.ainvoke is async, so we can call it directly
        result = await self._graph.ainvoke(
            {"messages": messages},
            config=runnable_config
        )
        
        return result
    
    def _extract_content(self, result: Dict[str, Any]) -> str:
        """
        Extract the main research content from ODR result.
        
        This is part of the "Output Mapping" layer.
        """
        # Try different possible keys where content might be stored
        content_keys = [
            "messages",
            "final_report", 
            "report",
            "research_brief",
            "content"
        ]
        
        for key in content_keys:
            if key in result and result[key]:
                value = result[key]
                
                # Handle messages array
                if key == "messages" and isinstance(value, list) and value:
                    last_message = value[-1]
                    if hasattr(last_message, 'content'):
                        return last_message.content
                    elif isinstance(last_message, dict) and 'content' in last_message:
                        return last_message['content']
                
                # Handle direct string values
                elif isinstance(value, str):
                    return value
                
                # Handle other structures
                elif hasattr(value, '__str__'):
                    return str(value)
        
        # If no content found, log the structure for debugging
        logger.warning(f"Could not extract content from ODR result. Keys: {list(result.keys())}")
        return ""
    
    def _extract_citations(self, result: Dict[str, Any], original_sources: List[ODRSource]) -> List[Dict[str, Any]]:
        """
        Extract citations from ODR result and combine with original sources.
        
        This is part of the "Citation Display Mapping" layer.
        """
        citations = []
        
        # Add original sources as citations
        for i, source in enumerate(original_sources):
            citation = {
                "id": f"source_{i + 1}",
                "type": source.source_type,
                "title": source.title or source.metadata.get('name', f"Source {i + 1}"),
                "url": source.url,
                "metadata": source.metadata,
                "content_preview": source.content[:200] + "..." if len(source.content) > 200 else source.content
            }
            citations.append(citation)
        
        # Extract citations from ODR research (if any)
        # ODR may store discovered sources in various places
        odr_citations = self._extract_odr_discovered_sources(result)
        
        # Add ODR-discovered citations with different IDs
        for i, citation in enumerate(odr_citations):
            citation["id"] = f"odr_{i + 1}"
            citations.append(citation)
        
        return citations
    
    def _extract_odr_discovered_sources(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract sources discovered by ODR during research."""
        discovered = []
        
        # Look for sources in research metadata
        if "research_units" in result:
            for unit in result["research_units"]:
                if isinstance(unit, dict) and "sources" in unit:
                    for source in unit["sources"]:
                        discovered.append({
                            "type": "web_research",
                            "title": source.get("title", "Research Source"),
                            "url": source.get("url"),
                            "metadata": {"discovered_by": "odr"}
                        })
        
        # Look for tool calls that might contain sources
        if "messages" in result:
            for message in result["messages"]:
                if hasattr(message, 'tool_calls'):
                    for tool_call in message.tool_calls:
                        if tool_call.get("name") == "tavily_search":
                            # Extract Tavily search results
                            pass  # TODO: Implement if needed
        
        return discovered
    
    def _extract_metadata(self, result: Dict[str, Any], odr_config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from ODR research process."""
        metadata = {
            "engine": "open_deep_research",
            "odr_version": "0.0.16",  # Could be extracted from package
            "config": odr_config,
            "result_keys": list(result.keys())
        }
        
        # Extract performance metrics if available
        if "processing_time" in result:
            metadata["odr_processing_time"] = result["processing_time"]
        
        if "iterations" in result:
            metadata["research_iterations"] = result["iterations"]
        
        # Extract research units info
        if "research_units" in result:
            metadata["research_units_count"] = len(result["research_units"])
        
        return metadata
    
    def _check_for_clarification(self, content: str) -> tuple[bool, Optional[str]]:
        """Check if the content contains clarification questions."""
        if not content:
            return False, None
            
        # Common patterns that indicate clarification questions
        clarification_indicators = [
            "please provide",
            "could you specify",
            "are you looking for",
            "do you want",
            "should the report",
            "is this for",
            "which specific",
            "what type of",
            "scope of the report",
            "specific areas of interest",
            "time frame",
            "purpose of the report"
        ]
        
        content_lower = content.lower()
        for indicator in clarification_indicators:
            if indicator in content_lower:
                return True, content
                
        # Check if content is mostly questions (ends with ?)
        lines = content.strip().split('\n')
        question_lines = [line for line in lines if line.strip().endswith('?')]
        if len(question_lines) > len(lines) * 0.5:  # More than 50% questions
            return True, content
            
        return False, None
    
    def _truncate_content(self, content: str, max_chars: int) -> str:
        """Truncate content while preserving readability."""
        if len(content) <= max_chars:
            return content
        
        # Try to truncate at sentence boundaries
        truncated = content[:max_chars]
        
        # Find the last sentence ending
        for delimiter in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
            last_sentence = truncated.rfind(delimiter)
            if last_sentence > max_chars * 0.8:  # Only if we don't lose too much content
                return truncated[:last_sentence + 1]
        
        # If no good sentence boundary, truncate at word boundary
        last_space = truncated.rfind(' ')
        if last_space > max_chars * 0.9:
            return truncated[:last_space] + "..."
        
        # Last resort: hard truncate
        return truncated + "..."


# Global service instance
_odr_service = None


async def get_odr_service() -> ODRService:
    """Get global ODR service instance."""
    global _odr_service
    if _odr_service is None:
        _odr_service = ODRService()
    return _odr_service


# Convenience functions for easy integration

async def generate_deep_research_report(
    query: str,
    documents: List[Dict[str, Any]] = None,
    web_sources: List[Dict[str, Any]] = None,
    docsend_sources: List[Dict[str, Any]] = None,
    config: Dict[str, Any] = None
) -> ODRResult:
    """
    Convenience function to generate deep research report.
    
    Args:
        query: Research question
        documents: List of document dicts with 'name' and 'content'
        web_sources: List of web source dicts with 'url' and 'content'
        docsend_sources: List of docsend dicts with 'url', 'content', and metadata
        config: Research configuration
        
    Returns:
        ODRResult with research findings
    """
    # Convert inputs to ODRSource objects
    sources = []
    
    if documents:
        for doc in documents:
            sources.append(ODRSource(
                content=doc.get('content', ''),
                source_type="document",
                metadata={'name': doc.get('name', 'Unknown Document')},
                title=doc.get('name')
            ))
    
    if web_sources:
        for web in web_sources:
            sources.append(ODRSource(
                content=web.get('content', ''),
                source_type="web",
                metadata={'status': web.get('status', 'success')},
                url=web.get('url'),
                title=web.get('title')
            ))
    
    if docsend_sources:
        for docsend in docsend_sources:
            sources.append(ODRSource(
                content=docsend.get('content', ''),
                source_type="docsend",
                metadata=docsend.get('metadata', {}),
                url=docsend.get('url'),
                title="DocSend Presentation"
            ))
    
    # Get service and generate report
    service = await get_odr_service()
    return await service.generate_report(query, sources, config)


async def check_odr_availability() -> Tuple[bool, Optional[str]]:
    """
    Check if ODR is available and return status.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    try:
        service = await get_odr_service()
        is_available = await service.is_available()
        error_message = service._last_error if not is_available else None
        return is_available, error_message
    except Exception as e:
        return False, str(e)