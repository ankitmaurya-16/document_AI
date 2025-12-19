import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import os

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
INDEX_PATH = "faiss_index.bin"

model = SentenceTransformer(EMBEDDING_MODEL)

def embed(texts):
    return model.encode(texts, normalize_embeddings=True).astype("float32")


if __name__ == "__main__":
    documents = [
        "Cats are small domesticated animals often kept as pets.",
        "Dogs are loyal animals and known as human companions.",
        "Python is a popular programming language.",
        "The stock market fluctuates based on economic conditions.",
        "Kittens require care and attention to stay healthy."
    ]

    print("Embedding documents...")
    doc_embeddings = embed(documents)

    dim = doc_embeddings.shape[1]
    print(f"Embedding dimension: {dim}")
    index=faiss.IndexFlatIP(dim)
    print("adding vectors to index")
    index.add(doc_embeddings)
    print(f"Total vectors in index: {index.ntotal}")
    faiss.write_index(index, INDEX_PATH)
    print(f"Index saved to index path {INDEX_PATH}")
    index=faiss.read_index(INDEX_PATH)
    print("Index loaded from the disk")
    query="how do i take care of the cat?"
    query_embedding=embed([query])
    k=3
    scores,indices=index.search(query_embedding,k)
    print("\nQuery: ", query)
    print("\nTop-K results:\n ");
    for rank, idx in enumerate(indices[0]):
        print(f"{rank+1}. Score: {scores[0][rank]:.3f}")
        print(f"   {documents[idx]}\n")