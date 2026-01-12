import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from retrieve import retrieve
from generate import generate_answer

question = "what is RAG?"
chunks = retrieve(question)
answer = generate_answer(question, chunks)
print(answer)
