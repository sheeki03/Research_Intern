import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Optional
import streamlit as st # For caching the model

# --- RAG Configuration ---
# Using a smaller, faster model for embeddings, adjust if needed.
# Common choices: 'all-MiniLM-L6-v2', 'msmarco-distilbert-base-v4'
# 'all-mpnet-base-v2' is larger but more performant.
DEFAULT_EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
TEXT_CHUNK_SIZE = 500  # Characters, not tokens. Adjust based on content and model context.
TEXT_CHUNK_OVERLAP = 50 # Characters
TOP_K_RESULTS = 3 # Number of relevant chunks to retrieve

# --- Model Loading (Cached) ---
@st.cache_resource(show_spinner=False) # Cache the embedding model loading
def get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> SentenceTransformer:
    """Loads and returns a SentenceTransformer model, caching it for efficiency."""
    with st.spinner(f"Loading embedding model ({model_name})... This may take a moment on first run."):
        model = SentenceTransformer(model_name)
    return model

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
        start += chunk_size - chunk_overlap # Move start pointer back by overlap for next chunk
    return chunks

# --- FAISS Indexing and Searching ---
def build_faiss_index(text_chunks: List[str], embedding_model: SentenceTransformer) -> Optional[faiss.Index]:
    """Builds a FAISS index from a list of text chunks.
    Returns the FAISS index, or None if no chunks or an error occurs.
    """
    if not text_chunks:
        return None
    try:
        with st.spinner(f"Generating embeddings for {len(text_chunks)} text chunks..."):
            embeddings = embedding_model.encode(text_chunks, convert_to_tensor=False, show_progress_bar=False)
        
        if embeddings is None or len(embeddings) == 0:
            st.warning("No embeddings were generated for the provided text chunks.")
            return None

        # FAISS expects float32
        embeddings = np.array(embeddings).astype('float32')
        
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)  # Using L2 distance for similarity
        index.add(embeddings)
        return index
    except Exception as e:
        st.error(f"Error building FAISS index: {e}")
        return None

def search_faiss_index(index: faiss.Index, query_text: str, embedding_model: SentenceTransformer, text_chunks: List[str], top_k: int = TOP_K_RESULTS) -> List[str]:
    """Searches the FAISS index for relevant text chunks based on a query string.
    Returns a list of the top_k most relevant text chunks.
    """
    if not query_text or index is None or not text_chunks:
        return []
    try:
        query_embedding = embedding_model.encode([query_text], convert_to_tensor=False)
        query_embedding = np.array(query_embedding).astype('float32')

        distances, indices = index.search(query_embedding, top_k)
        
        relevant_chunks = []
        for i in indices[0]: # indices is a 2D array, get the first (and only) row
            if 0 <= i < len(text_chunks):
                relevant_chunks.append(text_chunks[i])
        return relevant_chunks
    except Exception as e:
        st.error(f"Error searching FAISS index: {e}")
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
        results = search_faiss_index(index, query, model, sample_texts, top_k=2)
        print("Search results:")
        for res in results:
            print(f"- {res}")
    else:
        print("Failed to build FAISS index for the sample texts.") 