import json
import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict
from config import INDEX_DIR, FAISS_INDEX_PATH, METADATA_PATH, EMBEDDING_MODEL_NAME, TOP_K, SIMILARITY_THRESHOLD

model = SentenceTransformer(EMBEDDING_MODEL_NAME)

index = faiss.read_index(FAISS_INDEX_PATH)
index.hnsw.efSearch = 64
with open(METADATA_PATH, "r", encoding="utf-8") as f:
    metadata = json.load(f)

def embed(texts: List[str]) -> np.ndarray:
    return model.encode(
        texts,
        normalize_embeddings=True
    ).astype("float32")

def retrieve(query:str, top_k:int=TOP_K,threshold:float=SIMILARITY_THRESHOLD)->List[Dict]:
    query_embedding=embed([query])
    scores, indices=index.search(query_embedding, top_k)
    results=[]
    for score, idx in zip(scores[0], indices[0]):
        if score<threshold:
            continue
        chunk=metadata[idx]
        results.append({"chunk_id":chunk["chunk_id"],"source":chunk["source"],"text":chunk["text"],"score":float(score)})
    return results


