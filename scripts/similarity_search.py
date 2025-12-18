from sentence_transformers import SentenceTransformer
import numpy as np
model=SentenceTransformer("all-MiniLM-L6-v2")
def embed(text:str)->np.ndarray:
    return model.encode(text, normalize_embeddings=True)
def cosine_similarity(vec1: np.ndarray, vec2:np.ndarray)->float:
    return np.dot(vec1,vec2)

def similarity_search(documents, query, top_k=3):
    doc_embeddings=[embed(doc) for doc in documents]
    query_embedding=embed(query)
    scores=[]
    for doc, doc_emb in zip(documents, doc_embeddings):
        score=cosine_similarity(query_embedding, doc_emb)
        scores.append((doc,score))
    scores.sort(key=lambda x:x[1], reverse=True)
    return scores[:top_k]
if __name__ == "__main__":
    documents = [
        "Cats are small domesticated animals often kept as pets.",
        "Dogs are loyal animals and are known as human companions.",
        "Python is a popular programming language used for data science.",
        "The stock market fluctuates based on economic conditions.",
        "Kittens are young cats that require care and attention.",
        "Cats are common household pets. They require regular feeding, grooming,and veterinary care to stay healthy. Dogs are also popular pets but havedifferent care requirements."
    ]

    query = "Information about caring for a cat"

    print(f"Query: {query}\n")
    print("Top matching documents:\n")

    results = similarity_search(documents, query, top_k=10)

    for i, (doc, score) in enumerate(results, start=1):
        print(f"{i}. Similarity: {score:.3f}")
        print(f"   {doc}\n")