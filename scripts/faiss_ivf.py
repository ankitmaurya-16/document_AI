import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import time

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
N_LIST = 2       
N_PROBE = 1       
TOP_K = 3

model = SentenceTransformer(EMBEDDING_MODEL)

def embed(texts):
    return model.encode(texts, normalize_embeddings=True).astype("float32")


if __name__ == "__main__":
    documents = [
        "Cats are common household pets.",
        "Cats require regular feeding and grooming.",
        "Dogs are loyal animals and enjoy companionship.",
        "Stock markets fluctuate based on economic conditions.",
        "Kittens need care and attention to stay healthy."
    ]

    print("Embedding documents...")
    embeddings = embed(documents)
    dim = embeddings.shape[1]

    print("\nCreating IVF index...")
    quantizer = faiss.IndexFlatIP(dim) 
    index = faiss.IndexIVFFlat(
        quantizer,
        dim,
        N_LIST,
        faiss.METRIC_INNER_PRODUCT
    )

    print("Training IVF index...")
    index.train(embeddings) 

    print("Adding vectors to IVF index...")
    index.add(embeddings)

    index.nprobe = N_PROBE

    print(f"Total vectors indexed: {index.ntotal}")
    print(f"nlist = {N_LIST}, nprobe = {index.nprobe}")

    query = "How do I build nuclear reactor?"
    query_embedding = embed([query])

    start = time.time()
    scores, indices = index.search(query_embedding, TOP_K)
    end = time.time()

    print("\nQuery:", query)
    print(f"Query time: {(end - start) * 1000:.2f} ms\n")

    print("Top retrieved documents:\n")
    for rank, idx in enumerate(indices[0]):
        print(f"{rank + 1}. Score: {scores[0][rank]:.3f}")
        print(f"   {documents[idx]}\n")
