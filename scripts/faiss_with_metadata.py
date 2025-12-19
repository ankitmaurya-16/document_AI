import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 3

model = SentenceTransformer(EMBEDDING_MODEL)

def embed(texts):
    return model.encode(texts, normalize_embeddings=True).astype("float32")


if __name__ == "__main__":
    documents = [
        {
            "chunk_id": 0,
            "source": "pets.txt",
            "text": "Cats are common household pets."
        },
        {
            "chunk_id": 1,
            "source": "pets.txt",
            "text": "Cats require regular feeding and grooming."
        },
        {
            "chunk_id": 2,
            "source": "pets.txt",
            "text": "Dogs are loyal animals and enjoy companionship."
        },
        {
            "chunk_id": 3,
            "source": "finance.txt",
            "text": "Stock markets fluctuate based on economic conditions."
        },
        {
            "chunk_id": 4,
            "source": "pets.txt",
            "text": "Kittens need care and attention to stay healthy."
        }
    ]

    texts = [doc["text"] for doc in documents]

    print("Embedding chunks...")
    embeddings = embed(texts)

    dim = embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    print(f"Total vectors indexed: {index.ntotal}")

    query = "How do I take care of a cat?"
    query_embedding = embed([query])

    scores, indices = index.search(query_embedding, TOP_K)

    print("\nQuery:", query)
    print("\nTop retrieved chunks:\n")

    for rank, idx in enumerate(indices[0]):
        doc = documents[idx]
        score = scores[0][rank]

        print(f"{rank + 1}. Score: {score:.3f}")
        print(f"   Source: {doc['source']}")
        print(f"   Chunk ID: {doc['chunk_id']}")
        print(f"   Text: {doc['text']}\n")
