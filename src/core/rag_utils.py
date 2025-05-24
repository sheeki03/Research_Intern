# Temporarily disabled for macOS compatibility
import logging
import warnings

# Suppress the actual imports to prevent any loading
try:
    pass
    # from sentence_transformers import SentenceTransformer
except ImportError:
    pass

# Mock constants
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Disabled
TOP_K_RESULTS = 5

def get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    """DISABLED: SentenceTransformer model loading disabled for macOS compatibility."""
    raise RuntimeError("RAG functionality disabled on macOS due to SentenceTransformers segfault. Use alternative analysis methods.")

def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200):
    """DISABLED: Text chunking disabled for macOS compatibility."""
    raise RuntimeError("RAG functionality disabled on macOS due to SentenceTransformers segfault. Use alternative analysis methods.")

def build_faiss_index(text_chunks, embedding_model):
    """DISABLED: FAISS index building disabled for macOS compatibility."""
    raise RuntimeError("RAG functionality disabled on macOS due to SentenceTransformers segfault. Use alternative analysis methods.")

def search_faiss_index(index, query_text: str, embedding_model, text_chunks, top_k: int = TOP_K_RESULTS):
    """DISABLED: FAISS search disabled for macOS compatibility."""
    raise RuntimeError("RAG functionality disabled on macOS due to SentenceTransformers segfault. Use alternative analysis methods.")

# Log the disabling for debugging
logger = logging.getLogger(__name__)
logger.warning("RAG utilities disabled on macOS due to SentenceTransformers compatibility issues") 