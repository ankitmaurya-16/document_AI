import json
import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict

INDEX_DIR = "data/index"
FAISS_INDEX_PATH = os.path.join(INDEX_DIR, "faiss.index")
METADATA_PATH = os.path.join(INDEX_DIR, "metadata.json")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

TOP_K=5
SIMILARITY_THRESHOLD = 0.25

model = SentenceTransformer(EMBEDDING_MODEL)

index = faiss.read_index(FAISS_INDEX_PATH)

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

if __name__=="__main__":
    results=retrieve("What is RAG?")
    print(len(results))
    print(results[1]["chunk_id"])