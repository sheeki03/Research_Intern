import numpy as np
# Temporarily comment out problematic imports to avoid segfault
# import faiss
# from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Optional
import streamlit as st # For caching the model
# import torch

# --- RAG Configuration ---
# Using a smaller, faster model for embeddings, adjust if needed.
# Common choices: 'all-MiniLM-L6-v2', 'msmarco-distilbert-base-v4'
# 'all-mpnet-base-v2' is larger but more performant.
DEFAULT_EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
TEXT_CHUNK_SIZE = 500  # Characters, not tokens. Adjust based on content and model context.
TEXT_CHUNK_OVERLAP = 50 # Characters
TOP_K_RESULTS = 3 # Number of relevant chunks to retrieve

# --- Fallback Model Loading (Disabled for now to avoid segfault) ---
@st.cache_resource(show_spinner=False)
def get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    """Fallback: RAG functionality temporarily disabled due to macOS compatibility issues"""
    st.warning("⚠️ RAG/Chat functionality temporarily disabled due to macOS compatibility issues")
    return None

# --- Text Processing ---
def split_text_into_chunks(text: str, chunk_size: int = TEXT_CHUNK_SIZE, chunk_overlap: int = TEXT_CHUNK_OVERLAP) -> List[str]:
    """Splits a long text into smaller, overlapping chunks."""
    if not text or not isinstance(text, str):
        return []
        
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += chunk_size - chunk_overlap
    return chunks

# --- FAISS Indexing and Searching (Disabled) ---
def build_faiss_index(text_chunks: List[str], embedding_model) -> Optional[object]:
    """Fallback: FAISS indexing temporarily disabled"""
    st.info("🔧 FAISS indexing temporarily disabled - RAG chat not available")
    return None

def search_faiss_index(query_text: str, index, text_chunks: List[str], embedding_model, top_k: int = TOP_K_RESULTS) -> List[dict]:
    """Fallback: Search functionality temporarily disabled"""
    st.warning("⚠️ Search functionality temporarily disabled")
    return []

# --- Facade Function for RAG Context Building (Example Usage) ---
# This is more for testing or direct use if not integrated into a larger flow
# In our case, the building will happen in main.py when a report is ready.

if __name__ == '__main__':
    # Example usage (requires Streamlit context for caching if run directly, or remove @st.cache_resource for simple test)
    print(f"Loading embedding model ({DEFAULT_EMBEDDING_MODEL})...")
    model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL) # Direct load for non-Streamlit test
    
    sample_texts = [
        "The weather is sunny and warm today.",
        "Machine learning is a subset of artificial intelligence.",
        "Large language models can generate human-like text.",
        "Streamlit is a great tool for building web apps in Python.",
        "The quick brown fox jumps over the lazy dog."
    ]

    print("\nSplitting text into chunks (using one sample text for demo)...")
    long_text_example = "This is a long document about various topics. It discusses Python programming, data science techniques, and the future of AI. Python is versatile. Data science involves statistics. AI is evolving rapidly." * 5
    chunks = split_text_into_chunks(long_text_example)
    print(f"Original length: {len(long_text_example)}, Number of chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks[:2]): print(f" Chunk {i}: {chunk}...")

    print("\nBuilding FAISS index with sample texts...")
    index = build_faiss_index(sample_texts, model)

    if index:
        print(f"FAISS index built. Index size: {index.ntotal}")
        query = "What is related to AI?"
        print(f"\nSearching for: '{query}'")
        results = search_faiss_index(query, index, sample_texts, model, top_k=2)
        print("Search results:")
        for res in results:
            print(f"- {res['text']} (Distance: {res['distance']})")
    else:
        print("Failed to build FAISS index for the sample texts.") 