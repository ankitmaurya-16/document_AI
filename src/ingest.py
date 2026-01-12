import os
import json
import shutil
from typing import List, Dict
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from config import DOCS_DIR, INDEX_DIR, FAISS_INDEX_PATH, METADATA_PATH, CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL_NAME

model = SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed(texts: List[str]) -> np.ndarray:
    return model.encode(
        texts,
        normalize_embeddings=True
    ).astype("float32")


# Document Loading
def load_text_files(directory: str) -> Dict[str, str]:
    documents = {}
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            path = os.path.join(directory, filename)
            with open(path, "r", encoding="utf-8") as f:
                documents[filename] = f.read()
    return documents


# Word-safe Chunking
def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    chunks = []
    text_length = len(text)
    start = 0

    while start < text_length:
        approx_end = min(start + chunk_size, text_length)
        end = approx_end

        while end < text_length and not text[end].isspace():
            end += 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        next_start = end - overlap

        while next_start > start and next_start > 0 and not text[next_start - 1].isspace():
            next_start -= 1
        if next_start <= start:
            next_start = end  
        start = next_start

    return chunks


# Ingestion Pipeline
def ingest():
    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)
    os.makedirs(INDEX_DIR, exist_ok=True)

    print("Loading documents...")
    raw_docs = load_text_files(DOCS_DIR)

    all_chunks = []
    metadata = []

    print("Chunking documents...")
    for source, text in raw_docs.items():
        chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{source}_chunk_{i}"
            all_chunks.append(chunk)
            metadata.append({
                "chunk_id": chunk_id,
                "source": source,
                "text": chunk
            })

    print(f"Total chunks: {len(all_chunks)}")

    print("Embedding chunks...")
    embeddings = embed(all_chunks)
    dim = embeddings.shape[1]

    # FAISS HNSW Index
    print("Building HNSW index...")
    M = 32                 
    ef_construction = 200 

    index = faiss.IndexHNSWFlat(dim, M)
    index.hnsw.efConstruction = ef_construction
    index.metric_type = faiss.METRIC_INNER_PRODUCT

    print("Training index...")
    index.train(embeddings)

    print("Adding vectors...")
    index.add(embeddings)

    print(f"Vectors indexed: {index.ntotal}")

    # Save Artifacts
    print("Saving index and metadata...")
    faiss.write_index(index, FAISS_INDEX_PATH)

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("Ingestion complete.")


if __name__ == "__main__":
    ingest()
