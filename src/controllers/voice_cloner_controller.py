import asyncio
import time
import logging
import hashlib
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel, Field
from src.openrouter import OpenRouterClient
from src.config import AI_MODEL_OPTIONS

class VoiceClonerInput(BaseModel):
    """Input model for voice cloner functionality."""
    writing_example_1: str = Field(..., description="First writing example to analyze voice style")
    writing_example_2: str = Field(..., description="Second writing example to analyze voice style") 
    writing_example_3: str = Field(..., description="Third writing example to analyze voice style")
    new_piece_to_create: str = Field(..., description="Description of the new piece to create in the analyzed voice style")
    model: str = Field(..., description="AI model to use for voice cloning")
    username: str = Field(..., description="Username of the user making the request")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")

class VoiceClonerOutput(BaseModel):
    """Output model for voice cloner results."""
    final_piece: str = Field(..., description="The final voice-cloned piece")
    style_rules: str = Field(..., description="The extracted style rules used for voice cloning")
    confidence_score: int = Field(..., description="Confidence score (0-100) of how well the voice was cloned")
    iterations_completed: int = Field(..., description="Number of iterations completed during the refinement process")
    processing_time: float = Field(..., description="Time taken to process the request")

logger = logging.getLogger(__name__)

class RetryableError(Exception):
    """Base class for errors that should trigger retry logic."""
    pass

class APIRateLimitError(RetryableError):
    """Raised when API rate limit is exceeded."""
    pass

class APITimeoutError(RetryableError):
    """Raised when API request times out."""
    pass

class APIUnavailableError(RetryableError):
    """Raised when API service is temporarily unavailable."""
    pass

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    backoff_multiplier: float = 2.0
    jitter: bool = True  # Add random jitter to avoid thundering herd

class ErrorRecovery:
    """Advanced error recovery and retry logic for API failures."""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.retry_stats = {
            'total_attempts': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'rate_limit_hits': 0,
            'timeout_errors': 0,
            'service_unavailable': 0
        }
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff with jitter."""
        import random
        
        # Exponential backoff: base_delay * (multiplier ^ attempt)
        delay = self.config.base_delay * (self.config.backoff_multiplier ** attempt)
        
        # Cap at max_delay
        delay = min(delay, self.config.max_delay)
        
        # Add jitter to avoid thundering herd problem
        if self.config.jitter:
            jitter = random.uniform(0.1, 0.3) * delay
            delay += jitter
        
        return delay
    
    def classify_error(self, error: Exception) -> type:
        """Classify error to determine retry strategy."""
        error_str = str(error).lower()
        
        if 'rate limit' in error_str or '429' in error_str:
            return APIRateLimitError
        elif 'timeout' in error_str or 'timed out' in error_str:
            return APITimeoutError
        elif 'unavailable' in error_str or '503' in error_str or '502' in error_str:
            return APIUnavailableError
        elif 'connection' in error_str or 'network' in error_str:
            return APIUnavailableError
        else:
            return Exception  # Non-retryable
    
    async def retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry logic."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            self.retry_stats['total_attempts'] += 1
            
            try:
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    self.retry_stats['successful_retries'] += 1
                    logger.info(f"Operation succeeded after {attempt} retries")
                
                return result
                
            except Exception as e:
                last_exception = e
                error_type = self.classify_error(e)
                
                # Update error statistics
                if error_type == APIRateLimitError:
                    self.retry_stats['rate_limit_hits'] += 1
                elif error_type == APITimeoutError:
                    self.retry_stats['timeout_errors'] += 1
                elif error_type == APIUnavailableError:
                    self.retry_stats['service_unavailable'] += 1
                
                # Don't retry non-retryable errors
                if error_type == Exception or attempt >= self.config.max_retries:
                    if attempt > 0:
                        self.retry_stats['failed_retries'] += 1
                    logger.error(f"Operation failed after {attempt} retries: {str(e)}")
                    raise e
                
                # Calculate delay and wait
                delay = self.calculate_delay(attempt)
                logger.warning(f"Attempt {attempt + 1} failed ({error_type.__name__}): {str(e)}. Retrying in {delay:.2f}s...")
                
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        raise last_exception
    
    def get_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return dict(self.retry_stats)

class RequestPriority(Enum):
    """Request priority levels for queue management."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class QueuedRequest:
    """Represents a queued voice cloning request."""
    id: str
    input_data: 'VoiceClonerInput'
    priority: RequestPriority
    timestamp: datetime
    future: asyncio.Future
    
class RequestQueue:
    """Advanced request queue with priority and batching support."""
    
    def __init__(self, max_concurrent: int = 3, batch_size: int = 5, batch_timeout: float = 2.0):
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.queue: List[QueuedRequest] = []
        self.processing_semaphore = asyncio.Semaphore(max_concurrent)
        self.active_requests: Dict[str, QueuedRequest] = {}
        self.stats = {
            'total_requests': 0,
            'completed_requests': 0,
            'failed_requests': 0,
            'batched_requests': 0,
            'queue_length': 0,
            'average_wait_time': 0.0
        }
        
    def add_request(self, request: QueuedRequest) -> None:
        """Add a request to the queue with priority ordering."""
        self.queue.append(request)
        # Sort by priority (higher first) then by timestamp (older first)
        self.queue.sort(key=lambda r: (-r.priority.value, r.timestamp))
        self.stats['total_requests'] += 1
        self.stats['queue_length'] = len(self.queue)
        logger.info(f"Added request {request.id} to queue (priority: {request.priority.name})")
        
    def get_next_batch(self) -> List[QueuedRequest]:
        """Get the next batch of requests for processing."""
        if not self.queue:
            return []
            
        # Get up to batch_size requests with same priority
        batch = []
        target_priority = self.queue[0].priority
        
        for i, request in enumerate(self.queue):
            if len(batch) >= self.batch_size:
                break
            if request.priority != target_priority and batch:
                break  # Don't mix priorities in same batch
            batch.append(request)
            
        # Remove batched requests from queue
        for request in batch:
            self.queue.remove(request)
            
        self.stats['queue_length'] = len(self.queue)
        if len(batch) > 1:
            self.stats['batched_requests'] += len(batch)
            logger.info(f"Created batch of {len(batch)} requests (priority: {target_priority.name})")
            
        return batch
        
    def complete_request(self, request_id: str, success: bool = True) -> None:
        """Mark a request as completed."""
        if request_id in self.active_requests:
            request = self.active_requests[request_id]
            wait_time = (datetime.now() - request.timestamp).total_seconds()
            
            # Update statistics
            if success:
                self.stats['completed_requests'] += 1
            else:
                self.stats['failed_requests'] += 1
                
            # Update average wait time
            total_completed = self.stats['completed_requests'] + self.stats['failed_requests']
            if total_completed > 0:
                current_avg = self.stats['average_wait_time']
                self.stats['average_wait_time'] = ((current_avg * (total_completed - 1)) + wait_time) / total_completed
            
            del self.active_requests[request_id]
            logger.info(f"Completed request {request_id} (wait time: {wait_time:.2f}s)")
            
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            **self.stats,
            'active_requests': len(self.active_requests),
            'max_concurrent': self.max_concurrent
        }

class PerformanceOptimizer:
    """Performance optimization utilities for voice cloning."""
    
    @staticmethod
    def chunk_large_text(text: str, max_chunk_size: int = 2000, overlap: int = 200) -> List[str]:
        """Split large text into smaller chunks for processing."""
        if len(text) <= max_chunk_size:
            return [text]
            
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + max_chunk_size
            
            if end >= len(text):
                chunks.append(text[start:])
                break
                
            # Try to break at sentence boundary
            chunk = text[start:end]
            last_period = chunk.rfind('.')
            last_exclamation = chunk.rfind('!')
            last_question = chunk.rfind('?')
            
            sentence_end = max(last_period, last_exclamation, last_question)
            
            if sentence_end > start + max_chunk_size // 2:  # If we found a good break point
                end = start + sentence_end + 1
                
            chunks.append(text[start:end])
            start = end - overlap  # Overlap to maintain context
            
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks
        
    @staticmethod
    def estimate_processing_time(text_length: int, model: str) -> float:
        """Estimate processing time based on text length and model."""
        # Base time estimates (in seconds)
        base_times = {
            'qwen/qwen3-30b-a3b:free': 30,
            'qwen/qwen3-235b-a22b:free': 45,
            'google/gemini-2.5-pro-preview': 25,
            'openai/o3': 60,
            'openai/gpt-4.1': 35
        }
        
        base_time = base_times.get(model, 30)
        
        # Scale based on text length (rough estimate)
        length_factor = max(1.0, text_length / 1000)  # 1 second per 1000 chars minimum
        
        return base_time * length_factor
        
    @staticmethod
    def should_batch_requests(requests: List[QueuedRequest]) -> bool:
        """Determine if requests should be batched together."""
        if len(requests) < 2:
            return False
            
        # Check if all requests have similar characteristics
        first_request = requests[0]
        first_model = first_request.input_data.model
        first_priority = first_request.priority
        
        for request in requests[1:]:
            if (request.input_data.model != first_model or 
                request.priority != first_priority):
                return False
                
        return True

class VoiceStyleCache:
    """In-memory cache for voice style analysis results."""
    
    def __init__(self, max_size: int = 100, ttl_hours: int = 24):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        
    def _generate_cache_key(self, examples: list[str]) -> str:
        """Generate a cache key based on writing examples."""
        # Normalize and hash the examples for consistent caching
        normalized_examples = [ex.strip().lower() for ex in examples]
        combined_text = "|||".join(sorted(normalized_examples))
        return hashlib.md5(combined_text.encode()).hexdigest()
    
    def get(self, examples: list[str]) -> Optional[Dict[str, Any]]:
        """Get cached voice style analysis."""
        cache_key = self._generate_cache_key(examples)
        
        if cache_key in self.cache:
            cached_item = self.cache[cache_key]
            
            # Check if cache entry is still valid
            if datetime.now() - cached_item['timestamp'] < self.ttl:
                logger.info(f"Cache hit for voice style analysis: {cache_key[:8]}...")
                return cached_item['data']
            else:
                # Remove expired entry
                del self.cache[cache_key]
                logger.info(f"Cache entry expired and removed: {cache_key[:8]}...")
        
        logger.info(f"Cache miss for voice style analysis: {cache_key[:8]}...")
        return None
    
    def set(self, examples: list[str], analysis_data: Dict[str, Any]) -> None:
        """Cache voice style analysis results."""
        cache_key = self._generate_cache_key(examples)
        
        # Implement LRU eviction if cache is full
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
            logger.info(f"Cache eviction: removed {oldest_key[:8]}...")
        
        self.cache[cache_key] = {
            'data': analysis_data,
            'timestamp': datetime.now()
        }
        logger.info(f"Cached voice style analysis: {cache_key[:8]}...")
    
    def invalidate(self, examples: list[str]) -> bool:
        """Invalidate cache entry for specific examples."""
        cache_key = self._generate_cache_key(examples)
        if cache_key in self.cache:
            del self.cache[cache_key]
            logger.info(f"Cache invalidated: {cache_key[:8]}...")
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        logger.info("Voice style cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self.cache)
        valid_entries = sum(1 for item in self.cache.values() 
                          if datetime.now() - item['timestamp'] < self.ttl)
        
        return {
            'total_entries': total_entries,
            'valid_entries': valid_entries,
            'expired_entries': total_entries - valid_entries,
            'max_size': self.max_size,
            'ttl_hours': self.ttl.total_seconds() / 3600
        }

class VoiceClonerController:
    """Controller for voice cloner functionality."""
    
    # Input validation constants
    MIN_TEXT_LENGTH = 10
    MAX_TEXT_LENGTH = 50000
    MIN_EXAMPLE_LENGTH = 20
    MAX_EXAMPLE_LENGTH = 10000
    
    def __init__(self):
        self.openrouter_client = OpenRouterClient()
        self.style_cache = VoiceStyleCache(max_size=100, ttl_hours=24)
        self.request_queue = RequestQueue(max_concurrent=3, batch_size=5)
        self.performance_optimizer = PerformanceOptimizer()
        
        # Configure error recovery with API-specific settings
        retry_config = RetryConfig(
            max_retries=3,
            base_delay=2.0,  # Start with 2 seconds
            max_delay=120.0,  # Cap at 2 minutes
            backoff_multiplier=2.5,  # Aggressive backoff
            jitter=True
        )
        self.error_recovery = ErrorRecovery(retry_config)
    
    def _validate_input(self, input_data: VoiceClonerInput) -> None:
        """Validate input data before processing."""
        # Validate writing examples
        examples = [input_data.writing_example_1, input_data.writing_example_2, input_data.writing_example_3]
        
        for i, example in enumerate(examples, 1):
            if not example or not example.strip():
                raise ValueError(f"Writing example {i} cannot be empty")
            
            example_length = len(example.strip())
            if example_length < self.MIN_EXAMPLE_LENGTH:
                raise ValueError(f"Writing example {i} is too short (minimum {self.MIN_EXAMPLE_LENGTH} characters)")
            
            if example_length > self.MAX_EXAMPLE_LENGTH:
                raise ValueError(f"Writing example {i} is too long (maximum {self.MAX_EXAMPLE_LENGTH} characters)")
        
        # Validate text to reformat
        if not input_data.new_piece_to_create or not input_data.new_piece_to_create.strip():
            raise ValueError("Text to reformat cannot be empty")
        
        text_length = len(input_data.new_piece_to_create.strip())
        if text_length < self.MIN_TEXT_LENGTH:
            raise ValueError(f"Text to reformat is too short (minimum {self.MIN_TEXT_LENGTH} characters)")
        
        if text_length > self.MAX_TEXT_LENGTH:
            raise ValueError(f"Text to reformat is too long (maximum {self.MAX_TEXT_LENGTH} characters)")
        
        # Validate model
        if not input_data.model or input_data.model not in AI_MODEL_OPTIONS:
            raise ValueError(f"Invalid model selected: {input_data.model}")
        
        logger.info(f"Input validation passed - Examples: {[len(ex) for ex in examples]} chars, Text: {text_length} chars")
    
    async def _make_api_request_with_validation(self, prompt: str, model: str) -> str:
        """Make API request with validation and error classification for retry logic."""
        try:
            response_text = await self.openrouter_client.generate_response(
                prompt=prompt,
                system_prompt=None,  # Prompt already contains system instructions
                temperature=0.7,
                model_override=model
            )
            
            # Handle empty or invalid response
            if not response_text or len(response_text.strip()) < 10:
                raise APIUnavailableError("AI model returned an empty or very short response")
            
            # Check for common API error indicators in response
            if "error" in response_text.lower() or "sorry" in response_text.lower()[:100]:
                # This might be a temporary model issue
                raise APIUnavailableError("AI model encountered an error processing your request")
            
            return response_text
            
        except asyncio.TimeoutError:
            raise APITimeoutError("Request timed out")
        except Exception as e:
            error_str = str(e).lower()
            
            # Classify errors for appropriate retry behavior
            if 'rate limit' in error_str or '429' in error_str:
                raise APIRateLimitError(f"API rate limit exceeded: {str(e)}")
            elif 'timeout' in error_str or 'timed out' in error_str:
                raise APITimeoutError(f"Request timeout: {str(e)}")
            elif any(code in error_str for code in ['503', '502', '500', 'unavailable', 'connection', 'network']):
                raise APIUnavailableError(f"API service unavailable: {str(e)}")
            else:
                # Non-retryable error
                raise ValueError(f"API request failed: {str(e)}")
    
    def _analyze_single_text_style(self, text: str) -> dict:
        """Analyze style characteristics of a single text."""
        import re
        
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return {'avg_length': 0, 'formality': 'neutral', 'emotion': 'neutral', 'complexity': 'medium'}
        
        # Sentence length analysis
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
        
        # Formality analysis
        formal_indicators = ['however', 'therefore', 'furthermore', 'consequently', 'nevertheless']
        informal_indicators = ["i'm", "don't", "can't", "won't", 'yeah', 'ok', 'got', 'stuff']
        
        formal_count = sum(1 for word in formal_indicators if word in text.lower())
        informal_count = sum(1 for word in informal_indicators if word in text.lower())
        
        if formal_count > informal_count:
            formality = 'formal'
        elif informal_count > formal_count:
            formality = 'informal'
        else:
            formality = 'neutral'
        
        # Emotional tone analysis
        positive_indicators = ['great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'love', 'excited']
        negative_indicators = ['terrible', 'awful', 'hate', 'frustrated', 'annoyed', 'disappointed']
        enthusiastic_indicators = ['!', 'wow', 'amazing', 'incredible']
        
        positive_count = sum(1 for word in positive_indicators if word in text.lower())
        negative_count = sum(1 for word in negative_indicators if word in text.lower())
        enthusiastic_count = sum(1 for word in enthusiastic_indicators if word in text.lower())
        enthusiastic_count += text.count('!')
        
        if enthusiastic_count > 2:
            emotion = 'enthusiastic'
        elif positive_count > negative_count:
            emotion = 'positive'
        elif negative_count > positive_count:
            emotion = 'negative'
        else:
            emotion = 'neutral'
        
        # Complexity analysis
        complex_words = len([word for word in text.split() if len(word) > 7])
        total_words = len(text.split())
        complexity_ratio = complex_words / total_words if total_words > 0 else 0
        
        if complexity_ratio > 0.3:
            complexity = 'high'
        elif complexity_ratio > 0.15:
            complexity = 'medium'
        else:
            complexity = 'low'
        
        return {
            'avg_length': avg_sentence_length,
            'formality': formality,
            'emotion': emotion,
            'complexity': complexity,
            'exclamation_ratio': text.count('!') / len(sentences) if sentences else 0
        }
    
    def _analyze_input_characteristics(self, input_data: VoiceClonerInput) -> dict:
        """Analyze input characteristics to inform prompt adaptation with caching."""
        try:
            examples = [input_data.writing_example_1, input_data.writing_example_2, input_data.writing_example_3]
            text_to_reformat = input_data.new_piece_to_create
            
            # Check cache first for example analysis
            cached_analysis = self.style_cache.get(examples)
            if cached_analysis:
                logger.info("Using cached voice style analysis")
                # Add current text analysis to cached data
                cached_analysis['input_text'] = self._analyze_single_text_style(text_to_reformat)
                cached_analysis['text_length'] = len(text_to_reformat)
                return cached_analysis
            
            # Perform fresh analysis
            logger.info("Performing fresh voice style analysis")
            
            # Analyze all examples
            example_analyses = [self._analyze_single_text_style(ex) for ex in examples]
            text_analysis = self._analyze_single_text_style(text_to_reformat)
            
            # Aggregate example characteristics
            avg_characteristics = {
                'avg_length': sum(a['avg_length'] for a in example_analyses) / len(example_analyses),
                'formality': max(set(a['formality'] for a in example_analyses), 
                               key=[a['formality'] for a in example_analyses].count),
                'emotion': max(set(a['emotion'] for a in example_analyses), 
                             key=[a['emotion'] for a in example_analyses].count),
                'complexity': max(set(a['complexity'] for a in example_analyses), 
                                key=[a['complexity'] for a in example_analyses].count),
                'exclamation_ratio': sum(a['exclamation_ratio'] for a in example_analyses) / len(example_analyses)
            }
            
            result = {
                'examples': avg_characteristics,
                'input_text': text_analysis,
                'text_length': len(text_to_reformat),
                'example_lengths': [len(ex) for ex in examples]
            }
            
            # Cache the example analysis (without input_text since that varies)
            cache_data = {
                'examples': avg_characteristics,
                'example_lengths': [len(ex) for ex in examples]
            }
            self.style_cache.set(examples, cache_data)
            
            return result
            
        except Exception as e:
            logger.warning(f"Error analyzing input characteristics: {str(e)}")
            return {
                'examples': {'formality': 'neutral', 'emotion': 'neutral', 'complexity': 'medium'},
                'input_text': {'formality': 'neutral', 'emotion': 'neutral', 'complexity': 'medium'},
                'text_length': len(input_data.new_piece_to_create),
                'example_lengths': [len(input_data.writing_example_1)]
            }

    def _create_style_guidance(self, characteristics: dict) -> str:
        """Create specific style guidance based on analyzed characteristics."""
        style_elements = []
        
        examples_style = characteristics['examples']
        
        # Sentence length guidance
        if examples_style['avg_length'] < 10:
            style_elements.append("• Use short, punchy sentences (5-10 words typically)")
        elif examples_style['avg_length'] > 20:
            style_elements.append("• Use longer, more complex sentences with multiple clauses")
        else:
            style_elements.append("• Use moderate sentence lengths (10-20 words typically)")
        
        # Formality guidance
        if examples_style['formality'] == 'formal':
            style_elements.append("• Maintain formal tone with proper grammar and sophisticated vocabulary")
            style_elements.append("• Avoid contractions and colloquial expressions")
        elif examples_style['formality'] == 'informal':
            style_elements.append("• Use casual, conversational tone with contractions")
            style_elements.append("• Include informal expressions and relaxed grammar")
        else:
            style_elements.append("• Balance formal and informal elements appropriately")
        
        # Emotional tone guidance
        if examples_style['emotion'] == 'enthusiastic':
            style_elements.append("• Express enthusiasm and energy in the writing")
            style_elements.append("• Use exclamation points and positive language")
        elif examples_style['emotion'] == 'positive':
            style_elements.append("• Maintain an optimistic, positive tone")
        elif examples_style['emotion'] == 'negative':
            style_elements.append("• Reflect any critical or skeptical perspectives when appropriate")
        
        # Complexity guidance
        if examples_style['complexity'] == 'high':
            style_elements.append("• Use sophisticated vocabulary and complex sentence structures")
        elif examples_style['complexity'] == 'low':
            style_elements.append("• Keep language simple and accessible")
        else:
            style_elements.append("• Balance simple and complex language appropriately")
        
        return "\n".join(style_elements)

    def _create_few_shot_examples(self, characteristics: dict) -> str:
        """Create contextual few-shot examples based on characteristics."""
        examples_style = characteristics['examples']
        
        if examples_style['formality'] == 'formal' and examples_style['complexity'] == 'high':
            return """
<few_shot_examples>
Example transformation for formal, complex writing:
Before: "The software update includes new features."
After: "This comprehensive software update introduces several innovative features that significantly enhance user experience and operational efficiency."

Before: "Users reported issues with the system."
After: "Multiple users have documented various technical difficulties with the current system architecture, necessitating immediate attention and resolution."
</few_shot_examples>"""
        
        elif examples_style['formality'] == 'informal' and examples_style['emotion'] == 'enthusiastic':
            return """
<few_shot_examples>
Example transformation for informal, enthusiastic writing:
Before: "The software update includes new features."
After: "This update's got some amazing new features that you're gonna love!"

Before: "Users reported issues with the system."
After: "Hey, so some folks ran into a few hiccups with the system - but don't worry, we're on it!"
</few_shot_examples>"""
        
        else:
            return """
<few_shot_examples>
Example transformation for balanced writing:
Before: "The software update includes new features."
After: "The latest software update brings several new features that improve functionality."

Before: "Users reported issues with the system."
After: "Users have reported some issues with the system that we're working to resolve."
</few_shot_examples>"""

    def _create_voice_cloner_prompt(self, input_data: VoiceClonerInput) -> str:
        """Create an advanced, context-aware prompt for voice cloning and text reformatting."""
        # Analyze input characteristics for dynamic adaptation
        characteristics = self._analyze_input_characteristics(input_data)
        style_guidance = self._create_style_guidance(characteristics)
        few_shot_examples = self._create_few_shot_examples(characteristics)
        
        # Determine iteration count based on text complexity
        text_length = characteristics['text_length']
        if text_length > 2000:
            min_iterations = 60
        elif text_length > 1000:
            min_iterations = 55
        else:
            min_iterations = 50
        
        return f"""<instructions>
You are an expert "voice-cloner" and writer with advanced linguistic analysis capabilities.

Step 1 – Deep Voice Analysis:
Analyze the writing examples to identify:
• Sentence structure patterns and rhythm
• Vocabulary preferences and register
• Punctuation habits and emphasis patterns
• Transitional phrase usage
• Paragraph organization style
• Tone consistency and emotional markers

Step 2 – Build Comprehensive Style DNA:
Create a detailed style profile including:
{style_guidance}

Step 3 – Context-Aware Adaptation:
Consider the input text characteristics:
• Original text length: {text_length} characters
• Target formality level: {characteristics['examples']['formality']}
• Emotional tone: {characteristics['examples']['emotion']}
• Complexity level: {characteristics['examples']['complexity']}

{few_shot_examples}

Step 4 – Iterative Refinement Process (Minimum {min_iterations} iterations):
For each iteration:
1. Apply style analysis findings to current draft
2. Compare sentence patterns with voice examples
3. Adjust vocabulary, tone, and structure to match voice signature
4. Evaluate confidence score (0-100%) based on voice similarity
5. Document specific improvements made
6. Rewrite completely for natural flow

Step 5 – Quality Assurance:
Before finalizing, verify:
• All original information is preserved
• Voice signature is consistently applied
• Text flows naturally without AI-generated feel
• Confidence score is 90%+ 

Step 6 – Delivery:
Present only the final reformatted text, followed by style analysis in debug block.

Advanced Constraints:
• Maintain semantic equivalence while transforming stylistic elements
• Preserve factual accuracy and key details
• Ensure coherent narrative flow
• Eliminate AI writing patterns and generic phrasing
• Match the specific voice signature, not a generic style category
</instructions>

<voice_examples>
<example_1>
{input_data.writing_example_1}
</example_1>

<example_2>
{input_data.writing_example_2}
</example_2>

<example_3>
{input_data.writing_example_3}
</example_3>
</voice_examples>

<text_to_transform>
{input_data.new_piece_to_create}
</text_to_transform>

<iteration_requirements>
You must complete at least {min_iterations} refinement iterations. Track your progress explicitly:
- Iteration 1-10: Initial style extraction and basic application
- Iteration 11-20: Vocabulary and tone alignment
- Iteration 21-30: Sentence structure optimization
- Iteration 31-40: Flow and transition refinement
- Iteration 41-{min_iterations}: Final polish and voice signature verification

Do not deliver results before completing the minimum iteration count.
</iteration_requirements>"""

    def process_voice_cloning_sync(self, input_data: VoiceClonerInput) -> VoiceClonerOutput:
        """Process voice cloning request synchronously by running async method."""
        try:
            # Check if there's already a running event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's a running loop, we need to use a different approach
                logger.info("Detected running event loop, using thread-based execution")
                import concurrent.futures
                import threading
                
                # Create a new event loop in a separate thread
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(self.process_voice_cloning(input_data))
                    finally:
                        new_loop.close()
                
                # Run in thread to avoid event loop conflicts
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=600)  # 10 minute timeout
                    
            except RuntimeError:
                # No running event loop, safe to use asyncio.run()
                logger.info("No running event loop detected, using asyncio.run()")
                return asyncio.run(self.process_voice_cloning(input_data))
                
        except Exception as e:
            logger.error(f"Error in synchronous voice cloning wrapper: {str(e)}")
            raise e

    async def process_voice_cloning(self, input_data: VoiceClonerInput) -> VoiceClonerOutput:
        """Process voice cloning request asynchronously."""
        start_time = time.time()
        
        try:
            logger.info(f"Starting async voice cloning process for user: {input_data.username}, model: {input_data.model}")
            
            # Validate input before processing
            self._validate_input(input_data)
            
            # Create the prompt
            prompt = self._create_voice_cloner_prompt(input_data)
            logger.info(f"Generated prompt with length: {len(prompt)} characters")
            
            # Make the API request with enhanced error handling and retry logic
            logger.info("Making async API request with retry logic...")
            
            try:
                # Use error recovery with retry logic
                response_text = await self.error_recovery.retry_with_backoff(
                    self._make_api_request_with_validation, prompt, input_data.model
                )
                
                logger.info(f"API response received with length: {len(response_text) if response_text else 0}")
                
            except ValueError as ve:
                # Re-raise user-friendly validation errors
                raise ve
            except Exception as api_error:
                logger.error(f"API request failed after retries: {str(api_error)}")
                
                # Check if we should attempt graceful degradation
                error_str = str(api_error).lower()
                should_fallback = any(keyword in error_str for keyword in [
                    'rate limit', '429', 'unavailable', '503', '502', 'timeout', 'network', 'connection'
                ])
                
                if should_fallback:
                    logger.info("Attempting graceful degradation with fallback formatting")
                    try:
                        return await self._fallback_simple_reformat(input_data)
                    except Exception as fallback_error:
                        logger.error(f"Fallback method also failed: {str(fallback_error)}")
                        # Continue to original error handling
                
                # Provide more specific error messages based on error type
                if 'rate limit' in error_str or '429' in error_str:
                    raise ValueError("API rate limit exceeded. Please wait a few minutes and try again")
                elif 'timeout' in error_str:
                    raise ValueError("Request timed out after multiple attempts. Please try with shorter text or a different model")
                elif 'unavailable' in error_str or '503' in error_str or '502' in error_str:
                    raise ValueError("AI service is temporarily unavailable. Please try again in a few minutes")
                else:
                    raise ValueError(f"Failed to communicate with AI service: {str(api_error)}")
            
            # Extract final piece and debug information with enhanced error handling
            try:
                final_piece, style_rules, _, iterations = self._parse_response(response_text)
                
                # Validate extracted content
                if not final_piece or len(final_piece.strip()) < 10:
                    raise ValueError("AI model produced insufficient content. Please try again")
                
                # Calculate enhanced confidence score using multi-factor analysis
                confidence_score = self._calculate_enhanced_confidence_score(
                    input_data, final_piece, style_rules, response_text
                )
                
            except Exception as parse_error:
                logger.error(f"Error parsing AI response: {str(parse_error)}")
                raise ValueError(f"Failed to process AI response: {str(parse_error)}")
            
            processing_time = time.time() - start_time
            logger.info(f"Async voice cloning completed successfully in {processing_time:.2f} seconds")
            
            return VoiceClonerOutput(
                final_piece=final_piece,
                style_rules=style_rules,
                confidence_score=confidence_score,
                iterations_completed=iterations,
                processing_time=processing_time
            )
            
        except ValueError as ve:
            # User-friendly validation errors
            logger.warning(f"Validation error in async processing: {str(ve)}")
            raise ve
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error in async voice cloning process: {str(e)}")
            raise ValueError(f"An unexpected error occurred during voice cloning: {str(e)}")
    
    def _calculate_enhanced_confidence_score(self, input_data: VoiceClonerInput, final_piece: str, 
                                           style_rules: str, response_text: str) -> int:
        """Calculate enhanced confidence score using multi-factor analysis."""
        try:
            import re
            
            # Start with base score from AI response if available
            ai_confidence = 90  # Default
            confidence_matches = re.findall(r'(\d+)%', response_text)
            if confidence_matches:
                try:
                    extracted_confidence = int(confidence_matches[-1])
                    if 0 <= extracted_confidence <= 100:
                        ai_confidence = extracted_confidence
                except (ValueError, IndexError):
                    pass
            
            # Factor 1: Style Similarity Analysis (25% weight)
            style_score = self._analyze_style_similarity(input_data, final_piece)
            
            # Factor 2: Tone Consistency (20% weight)  
            tone_score = self._analyze_tone_consistency(input_data, final_piece)
            
            # Factor 3: Vocabulary Match (20% weight)
            vocab_score = self._analyze_vocabulary_match(input_data, final_piece)
            
            # Factor 4: Sentence Structure Alignment (15% weight)
            structure_score = self._analyze_sentence_structure(input_data, final_piece)
            
            # Factor 5: Content Quality (10% weight)
            quality_score = self._analyze_content_quality(final_piece, style_rules)
            
            # Factor 6: AI Model Confidence (10% weight)
            ai_score = ai_confidence
            
            # Calculate weighted confidence score
            weighted_score = (
                (style_score * 0.25) +
                (tone_score * 0.20) +
                (vocab_score * 0.20) +
                (structure_score * 0.15) +
                (quality_score * 0.10) +
                (ai_score * 0.10)
            )
            
            # Ensure score is within valid range
            final_confidence = max(0, min(100, int(weighted_score)))
            
            logger.info(f"Enhanced confidence calculation - Style: {style_score}, Tone: {tone_score}, "
                       f"Vocab: {vocab_score}, Structure: {structure_score}, Quality: {quality_score}, "
                       f"AI: {ai_score}, Final: {final_confidence}")
            
            return final_confidence
            
        except Exception as e:
            logger.error(f"Error calculating enhanced confidence score: {str(e)}")
            # Fallback to simple extraction
            return ai_confidence

    def _analyze_style_similarity(self, input_data: VoiceClonerInput, final_piece: str) -> int:
        """Analyze style similarity between examples and output."""
        try:
            examples = [input_data.writing_example_1, input_data.writing_example_2, input_data.writing_example_3]
            
            # Analyze average sentence length similarity
            def get_avg_sentence_length(text: str) -> float:
                import re
                sentences = re.split(r'[.!?]+', text)
                sentences = [s.strip() for s in sentences if s.strip()]
                if not sentences:
                    return 0
                return sum(len(s.split()) for s in sentences) / len(sentences)
            
            example_avg_lengths = [get_avg_sentence_length(ex) for ex in examples]
            final_avg_length = get_avg_sentence_length(final_piece)
            
            if not example_avg_lengths or final_avg_length == 0:
                return 70  # Default if can't analyze
            
            # Calculate similarity based on sentence length consistency
            avg_example_length = sum(example_avg_lengths) / len(example_avg_lengths)
            length_diff = abs(avg_example_length - final_avg_length)
            length_similarity = max(0, 100 - (length_diff * 5))  # 5 points per word difference
            
            return min(100, max(50, int(length_similarity)))  # Clamp between 50-100
            
        except Exception:
            return 75  # Safe default

    def _analyze_tone_consistency(self, input_data: VoiceClonerInput, final_piece: str) -> int:
        """Analyze tone consistency between examples and output."""
        try:
            examples = [input_data.writing_example_1, input_data.writing_example_2, input_data.writing_example_3]
            
            def count_punctuation_patterns(text: str) -> dict:
                import re
                return {
                    'exclamations': len(re.findall(r'!', text)),
                    'questions': len(re.findall(r'\?', text)),
                    'commas': len(re.findall(r',', text)),
                    'semicolons': len(re.findall(r';', text)),
                    'periods': len(re.findall(r'\.', text))
                }
            
            # Get punctuation patterns from examples
            example_patterns = [count_punctuation_patterns(ex) for ex in examples]
            final_patterns = count_punctuation_patterns(final_piece)
            
            # Calculate average patterns from examples
            avg_patterns = {}
            for key in example_patterns[0].keys():
                total = sum(patterns[key] for patterns in example_patterns)
                text_length = sum(len(ex) for ex in examples)
                avg_patterns[key] = total / text_length if text_length > 0 else 0
            
            # Compare with final piece patterns
            final_length = len(final_piece)
            final_normalized = {k: v / final_length if final_length > 0 else 0 
                              for k, v in final_patterns.items()}
            
            # Calculate similarity score
            similarities = []
            for key in avg_patterns.keys():
                if avg_patterns[key] == 0 and final_normalized[key] == 0:
                    similarities.append(1.0)
                elif avg_patterns[key] == 0 or final_normalized[key] == 0:
                    similarities.append(0.5)
                else:
                    ratio = min(avg_patterns[key], final_normalized[key]) / max(avg_patterns[key], final_normalized[key])
                    similarities.append(ratio)
            
            tone_score = sum(similarities) / len(similarities) * 100
            return min(100, max(50, int(tone_score)))
            
        except Exception:
            return 75  # Safe default

    def _analyze_vocabulary_match(self, input_data: VoiceClonerInput, final_piece: str) -> int:
        """Analyze vocabulary match between examples and output."""
        try:
            examples = [input_data.writing_example_1, input_data.writing_example_2, input_data.writing_example_3]
            
            def get_word_frequency(text: str) -> dict:
                import re
                words = re.findall(r'\b\w+\b', text.lower())
                freq = {}
                for word in words:
                    if len(word) > 3:  # Only consider words longer than 3 chars
                        freq[word] = freq.get(word, 0) + 1
                return freq
            
            # Get vocabulary from examples
            example_vocab = {}
            for example in examples:
                vocab = get_word_frequency(example)
                for word, count in vocab.items():
                    example_vocab[word] = example_vocab.get(word, 0) + count
            
            final_vocab = get_word_frequency(final_piece)
            
            if not example_vocab or not final_vocab:
                return 75
            
            # Calculate vocabulary overlap
            common_words = set(example_vocab.keys()) & set(final_vocab.keys())
            example_unique = set(example_vocab.keys()) - common_words
            final_unique = set(final_vocab.keys()) - common_words
            
            # Score based on overlap vs unique words
            if len(example_vocab) == 0:
                return 75
            
            overlap_ratio = len(common_words) / (len(common_words) + len(example_unique) + len(final_unique))
            vocab_score = overlap_ratio * 100
            
            return min(100, max(60, int(vocab_score)))
            
        except Exception:
            return 75  # Safe default

    def _analyze_sentence_structure(self, input_data: VoiceClonerInput, final_piece: str) -> int:
        """Analyze sentence structure similarity."""
        try:
            examples = [input_data.writing_example_1, input_data.writing_example_2, input_data.writing_example_3]
            
            def analyze_structure(text: str) -> dict:
                import re
                sentences = re.split(r'[.!?]+', text)
                sentences = [s.strip() for s in sentences if s.strip()]
                
                if not sentences:
                    return {'avg_length': 0, 'complex_ratio': 0, 'avg_commas': 0}
                
                lengths = [len(s.split()) for s in sentences]
                complex_sentences = sum(1 for s in sentences if ',' in s or ';' in s or ' and ' in s or ' but ' in s)
                commas_per_sentence = sum(s.count(',') for s in sentences) / len(sentences)
                
                return {
                    'avg_length': sum(lengths) / len(lengths),
                    'complex_ratio': complex_sentences / len(sentences),
                    'avg_commas': commas_per_sentence
                }
            
            # Analyze examples
            example_structures = [analyze_structure(ex) for ex in examples]
            final_structure = analyze_structure(final_piece)
            
            # Calculate average structure from examples
            avg_structure = {}
            for key in example_structures[0].keys():
                avg_structure[key] = sum(struct[key] for struct in example_structures) / len(example_structures)
            
            # Compare structures
            similarities = []
            for key in avg_structure.keys():
                if avg_structure[key] == 0 and final_structure[key] == 0:
                    similarities.append(1.0)
                elif avg_structure[key] == 0 or final_structure[key] == 0:
                    similarities.append(0.7)
                else:
                    diff = abs(avg_structure[key] - final_structure[key])
                    max_val = max(avg_structure[key], final_structure[key])
                    similarity = max(0, 1 - (diff / max_val))
                    similarities.append(similarity)
            
            structure_score = sum(similarities) / len(similarities) * 100
            return min(100, max(60, int(structure_score)))
            
        except Exception:
            return 80  # Safe default

    def _analyze_content_quality(self, final_piece: str, style_rules: str) -> int:
        """Analyze overall content quality."""
        try:
            quality_score = 80  # Base score
            
            # Check for appropriate length
            if len(final_piece) < 50:
                quality_score -= 20
            elif len(final_piece) > 10000:
                quality_score -= 10
            
            # Check for style rules presence
            if "not available" in style_rules.lower() or len(style_rules) < 20:
                quality_score -= 5
            else:
                quality_score += 5
            
            # Check for coherence indicators
            import re
            sentences = re.split(r'[.!?]+', final_piece)
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if len(sentences) > 1:
                # Check for transition words/phrases
                transitions = ['however', 'therefore', 'moreover', 'furthermore', 'additionally', 
                             'consequently', 'meanwhile', 'also', 'and', 'but', 'so']
                transition_count = sum(1 for sentence in sentences 
                                     for transition in transitions 
                                     if transition in sentence.lower())
                
                if transition_count > 0:
                    quality_score += min(10, transition_count * 2)
            
            return min(100, max(50, quality_score))
            
        except Exception:
            return 80  # Safe default

    def _parse_response(self, response_text: str) -> tuple[str, str, int, int]:
        """Parse the AI response to extract final piece and debug info."""
        try:
            if not response_text or not response_text.strip():
                raise ValueError("Empty response text provided for parsing")
            
            # Split by debug block
            if "```debug" in response_text:
                parts = response_text.split("```debug")
                final_piece = parts[0].strip()
                debug_section = parts[1].split("```")[0].strip() if len(parts) > 1 else ""
            elif "```" in response_text:
                # Handle cases where debug block might be malformed
                parts = response_text.split("```")
                final_piece = parts[0].strip()
                debug_section = parts[1].strip() if len(parts) > 1 else ""
            else:
                final_piece = response_text.strip()
                debug_section = ""
            
            # Validate final piece exists and has content
            if not final_piece or len(final_piece.strip()) < 10:
                raise ValueError("Final piece is empty or too short after parsing")
            
            # Remove any confidence scores or iteration counts from the final piece
            import re
            # Remove patterns like "Confidence: 95%" or "95% confidence" from final text
            final_piece = re.sub(r'(?i)confidence[:\s]*\d+%?', '', final_piece)
            final_piece = re.sub(r'(?i)\d+%?\s*confidence', '', final_piece)
            # Remove patterns like "Iteration 50" or "Round 52" from final text
            final_piece = re.sub(r'(?i)iteration\s*\d+', '', final_piece)
            final_piece = re.sub(r'(?i)round\s*\d+', '', final_piece)
            # Clean up extra whitespace
            final_piece = re.sub(r'\s+', ' ', final_piece).strip()
            
            # Final validation after cleanup
            if not final_piece or len(final_piece.strip()) < 10:
                raise ValueError("Final piece became empty or too short after cleanup")
            
            # Extract style rules from debug section
            style_rules = debug_section if debug_section else "Style rules not available in response"
            
            # Extract iteration count with validation
            iterations = 50  # Default minimum as specified in system prompt
            iteration_matches = re.findall(r'iteration\s*(\d+)|round\s*(\d+)', response_text.lower())
            if iteration_matches:
                try:
                    all_iterations = [int(m[0]) if m[0] else int(m[1]) for m in iteration_matches]
                    max_iterations = max(all_iterations)
                    # Validate iteration count is reasonable (1-1000)
                    if 1 <= max_iterations <= 1000:
                        iterations = max_iterations
                    else:
                        logger.warning(f"Invalid iteration count extracted: {max_iterations}, using default")
                except (ValueError, IndexError):
                    logger.warning("Could not parse iteration count, using default")
            
            # Note: confidence_score will be calculated separately in the calling method
            logger.info(f"Successfully parsed response: {len(final_piece)} chars, iterations: {iterations}")
            return final_piece, style_rules, 0, iterations  # confidence_score placeholder
            
        except ValueError as ve:
            # Re-raise validation errors with context
            logger.error(f"Validation error parsing response: {str(ve)}")
            raise ve
        except Exception as e:
            # Handle unexpected parsing errors gracefully
            logger.error(f"Unexpected error parsing response: {str(e)}")
            # Return the original response as final piece if parsing fails completely
            if response_text and len(response_text.strip()) >= 10:
                return response_text.strip(), "Error extracting style rules", 0, 50
            else:
                raise ValueError("Response parsing failed and original text is insufficient")
    
    async def process_multiple_voice_cloning(self, input_list: list[VoiceClonerInput]) -> list[VoiceClonerOutput]:
        """Process multiple voice cloning requests concurrently."""
        if not input_list:
            return []
        
        logger.info(f"Starting concurrent processing of {len(input_list)} voice cloning requests")
        
        # Create semaphore to limit concurrent requests to avoid overwhelming the API
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
        
        async def process_with_semaphore(input_data: VoiceClonerInput) -> VoiceClonerOutput:
            async with semaphore:
                return await self.process_voice_cloning(input_data)
        
        try:
            # Process all requests concurrently
            tasks = [process_with_semaphore(input_data) for input_data in input_list]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Convert exceptions to proper error outputs
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing request {i+1}: {str(result)}")
                    # Create error output
                    error_output = VoiceClonerOutput(
                        final_piece=f"Error processing request: {str(result)}",
                        style_rules="Error occurred during processing",
                        confidence_score=0,
                        iterations_completed=0,
                        processing_time=0.0
                    )
                    processed_results.append(error_output)
                else:
                    processed_results.append(result)
            
            logger.info(f"Completed concurrent processing of {len(input_list)} requests")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in concurrent voice cloning processing: {str(e)}")
            raise ValueError(f"Failed to process concurrent requests: {str(e)}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get voice style cache statistics."""
        return self.style_cache.get_stats()
    
    def clear_cache(self) -> None:
        """Clear the voice style cache."""
        self.style_cache.clear()
    
    def invalidate_cache_for_examples(self, examples: list[str]) -> bool:
        """Invalidate cache for specific writing examples."""
        return self.style_cache.invalidate(examples)
    
    async def process_with_streaming(self, input_data: VoiceClonerInput, 
                                   callback=None) -> VoiceClonerOutput:
        """Process voice cloning with streaming updates for large texts."""
        try:
            text_length = len(input_data.new_piece_to_create)
            
            # For large texts, use chunking
            if text_length > 5000:
                logger.info(f"Using chunked processing for large text: {text_length} chars")
                return await self._process_chunked_text(input_data, callback)
            else:
                # Regular processing for smaller texts
                return await self.process_voice_cloning(input_data)
                
        except Exception as e:
            logger.error(f"Error in streaming processing: {str(e)}")
            raise ValueError(f"Streaming processing failed: {str(e)}")
    
    async def _process_chunked_text(self, input_data: VoiceClonerInput, 
                                  callback=None) -> VoiceClonerOutput:
        """Process large text by breaking it into chunks."""
        start_time = time.time()
        
        # Split text into chunks
        chunks = self.performance_optimizer.chunk_large_text(
            input_data.new_piece_to_create, max_chunk_size=2000
        )
        
        processed_chunks = []
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks):
            if callback:
                await callback(f"Processing chunk {i+1}/{total_chunks}")
            
            # Create input for this chunk
            chunk_input = VoiceClonerInput(
                writing_example_1=input_data.writing_example_1,
                writing_example_2=input_data.writing_example_2,
                writing_example_3=input_data.writing_example_3,
                new_piece_to_create=chunk,
                model=input_data.model,
                username=input_data.username,
                session_id=input_data.session_id
            )
            
            # Process chunk
            chunk_result = await self.process_voice_cloning(chunk_input)
            processed_chunks.append(chunk_result.final_piece)
            
            if callback:
                progress = ((i + 1) / total_chunks) * 100
                await callback(f"Progress: {progress:.1f}% ({i+1}/{total_chunks} chunks)")
        
        # Combine results
        final_text = " ".join(processed_chunks)
        processing_time = time.time() - start_time
        
        # Calculate aggregate metrics
        avg_confidence = sum(chunk.confidence_score for chunk in []) / len(chunks) if chunks else 90
        total_iterations = sum(chunk.iterations_completed for chunk in []) if chunks else 50
        
        return VoiceClonerOutput(
            final_piece=final_text,
            style_rules=f"Processed {total_chunks} chunks with consistent style application",
            confidence_score=int(avg_confidence),
            iterations_completed=total_iterations,
            processing_time=processing_time
        )
    
    async def process_with_queue(self, input_data: VoiceClonerInput, 
                               priority: RequestPriority = RequestPriority.NORMAL) -> VoiceClonerOutput:
        """Process voice cloning request through the optimized queue system."""
        import uuid
        
        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        
        queued_request = QueuedRequest(
            id=request_id,
            input_data=input_data,
            priority=priority,
            timestamp=datetime.now(),
            future=future
        )
        
        # Add to queue
        self.request_queue.add_request(queued_request)
        self.request_queue.active_requests[request_id] = queued_request
        
        try:
            # Process the request
            async with self.request_queue.processing_semaphore:
                logger.info(f"Processing queued request {request_id}")
                
                # Estimate processing time
                text_length = len(input_data.new_piece_to_create)
                estimated_time = self.performance_optimizer.estimate_processing_time(
                    text_length, input_data.model
                )
                logger.info(f"Estimated processing time: {estimated_time:.1f}s")
                
                # Process the request
                result = await self.process_voice_cloning(input_data)
                
                # Mark as completed
                self.request_queue.complete_request(request_id, success=True)
                future.set_result(result)
                
                return result
                
        except Exception as e:
            logger.error(f"Error processing queued request {request_id}: {str(e)}")
            self.request_queue.complete_request(request_id, success=False)
            future.set_exception(e)
            raise e
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get request queue statistics."""
        return self.request_queue.get_stats()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        return {
            'cache_stats': self.get_cache_stats(),
            'queue_stats': self.get_queue_stats(),
            'optimizer_available': True
        }
    
    def get_available_models(self) -> dict:
        """Get available AI models."""
        return AI_MODEL_OPTIONS
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """Get error recovery and retry statistics."""
        return self.error_recovery.get_stats()
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health metrics."""
        retry_stats = self.get_retry_stats()
        cache_stats = self.style_cache.get_stats()
        queue_stats = self.request_queue.get_stats()
        
        # Calculate success rate
        total_attempts = retry_stats['total_attempts']
        successful_attempts = total_attempts - retry_stats['failed_retries']
        success_rate = (successful_attempts / total_attempts * 100) if total_attempts > 0 else 100
        
        return {
            'success_rate': round(success_rate, 2),
            'cache_hit_rate': round((cache_stats['valid_entries'] / max(cache_stats['total_entries'], 1)) * 100, 2),
            'average_queue_wait': queue_stats['average_wait_time'],
            'active_requests': queue_stats['active_requests'],
            'retry_stats': retry_stats,
            'cache_stats': cache_stats,
            'queue_stats': queue_stats
        }
    
    async def _fallback_simple_reformat(self, input_data: VoiceClonerInput) -> VoiceClonerOutput:
        """Fallback method when main API fails - provides basic text reformatting."""
        logger.warning("Using fallback simple reformat due to API failures")
        
        start_time = time.time()
        
        # Basic text cleaning and formatting
        text = input_data.new_piece_to_create.strip()
        
        # Simple improvements: fix spacing, basic sentence structure
        import re
        
        # Fix multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Ensure proper sentence spacing
        text = re.sub(r'([.!?])\s*', r'\1 ', text)
        
        # Remove trailing spaces
        text = text.strip()
        
        # Basic capitalization
        sentences = re.split(r'([.!?]\s+)', text)
        formatted_sentences = []
        
        for sentence in sentences:
            if sentence.strip() and not re.match(r'[.!?]\s*$', sentence):
                sentence = sentence.strip()
                if sentence:
                    sentence = sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper()
                formatted_sentences.append(sentence)
            else:
                formatted_sentences.append(sentence)
        
        formatted_text = ''.join(formatted_sentences)
        
        processing_time = time.time() - start_time
        
        return VoiceClonerOutput(
            final_piece=formatted_text,
            style_rules="Fallback mode: Basic text formatting applied due to AI service unavailability",
            confidence_score=40,  # Low confidence for fallback
            iterations_completed=1,
            processing_time=processing_time
        )