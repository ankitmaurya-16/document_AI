import json
import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
from config import INDEX_DIR, FAISS_INDEX_PATH, METADATA_PATH, EMBEDDING_MODEL_NAME, TOP_K, SIMILARITY_THRESHOLD

model = SentenceTransformer(EMBEDDING_MODEL_NAME)

# Global variables for lazy loading
_index: Optional[faiss.Index] = None
_metadata: Optional[List[Dict]] = None


def load_index_and_metadata():
    """Load FAISS index and metadata lazily."""
    global _index, _metadata
    
    if _index is None or _metadata is None:
        if not os.path.exists(FAISS_INDEX_PATH):
            raise FileNotFoundError(
                f"FAISS index not found at {FAISS_INDEX_PATH}. "
                "Please ingest documents first."
            )
        if not os.path.exists(METADATA_PATH):
            raise FileNotFoundError(
                f"Metadata not found at {METADATA_PATH}. "
                "Please ingest documents first."
            )
        
        _index = faiss.read_index(FAISS_INDEX_PATH)
        _index.hnsw.efSearch = 64
        
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _metadata = json.load(f)
    
    return _index, _metadata


def reload_index():
    """Force reload of index and metadata. Call this after ingestion."""
    global _index, _metadata
    _index = None
    _metadata = None
    return load_index_and_metadata()


def embed(texts: List[str]) -> np.ndarray:
    return model.encode(
        texts,
        normalize_embeddings=True
    ).astype("float32")


def retrieve(query:str, top_k:int=TOP_K,threshold:float=SIMILARITY_THRESHOLD)->List[Dict]:
    index, metadata = load_index_and_metadata()
    
    query_embedding=embed([query])
    scores, indices=index.search(query_embedding, top_k)
    
    print(f"DEBUG retrieve(): Found {len(scores[0])} results from FAISS")
    print(f"DEBUG retrieve(): Scores: {scores[0][:5]}")
    print(f"DEBUG retrieve(): Threshold: {threshold}")
    
    results=[]
    for score, idx in zip(scores[0], indices[0]):
        print(f"  Checking: score={score:.4f}, threshold={threshold}, pass={score >= threshold}")
        if score<threshold:
            continue
        chunk=metadata[idx]
        results.append({"chunk_id":chunk["chunk_id"],"source":chunk["source"],"text":chunk["text"],"score":float(score)})
    
    print(f"DEBUG retrieve(): Returning {len(results)} chunks after threshold filter")
    return results


# Alias for backwards compatibility
def retrieve_top_chunks(query: str, top_k: int = TOP_K, threshold: float = SIMILARITY_THRESHOLD) -> List[Dict]:
    """Alias for retrieve() function."""
    return retrieve(query, top_k, threshold)