# from openai import OpenAI
# from dotenv import load_dotenv
# import os
# import numpy as np

# load_dotenv()
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# EMBEDDING_MODEL = "text-embedding-3-small"


# def get_embedding(text: str) -> np.ndarray:
#     response = client.embeddings.create(
#         model=EMBEDDING_MODEL,
#         input=text
#     )
#     return np.array(response.data[0].embedding)


# def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
#     return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


# if __name__ == "__main__":
#     texts = [
#         # Similar meaning
#         "A cat is sleeping on the sofa.",
#         "A kitten is lying on the couch.",

#         # Same meaning, rephrased
#         "I love programming in Python.",
#         "Python is my favorite language to code in.",

#         # Unrelated
#         "The stock market crashed yesterday.",
#         "I cooked pasta for dinner."
#     ]

#     print("Generating embeddings...\n")

#     embeddings = [get_embedding(text) for text in texts]

#     print("Cosine similarity matrix:\n")

#     for i in range(len(texts)):
#         for j in range(i + 1, len(texts)):
#             sim = cosine_similarity(embeddings[i], embeddings[j])
#             print(f"Similarity [{i}] ↔ [{j}]: {sim:.3f}")
#             print(f"  '{texts[i]}'")
#             print(f"  '{texts[j]}'\n")


from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embedding(text: str) -> np.ndarray:
    return model.encode(text, normalize_embeddings=True)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    return np.dot(vec1, vec2) 


if __name__ == "__main__":
    texts = [
        # Similar meaning
        "A cat is sleeping on the sofa.",
        "A kitten is lying on the couch.",

        # Same meaning, rephrased
        "I love programming in Python.",
        "Python is my favorite language to code in.",

        # Unrelated
        "The stock market crashed yesterday.",
        "I cooked pasta for dinner."
    ]

    print("Generating embeddings (local, no API)...\n")

    embeddings = [get_embedding(text) for text in texts]

    print("Cosine similarity scores:\n")

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            print(f"Similarity [{i}] ↔ [{j}]: {sim:.3f}")
            print(f"  '{texts[i]}'")
            print(f"  '{texts[j]}'\n")
