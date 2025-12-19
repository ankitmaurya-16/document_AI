from src.retrieve import retrieve

results=retrieve("What is RAG?")
print(len(results))
print(results[0].keys())