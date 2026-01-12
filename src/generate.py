from typing import List, Dict
from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()
client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def build_prompt(question:str,context_chunks:List[Dict])->str:
    context_text="\n\n".join(f"[Source:{chunk['source']}]\n{chunk['text']}" for chunk in context_chunks)
    prompt=f"""You are a careful assistant. Answer the question using ONLY the context below and also you can use multiple context. Also provide the citations of the text. If the answer is not contained in the context or the context is not appropriate for the question, say: "I don't have enough information to answer this question." Context:{context_text}, Question:{question}"""
    return prompt.strip()

def generate_answer(question:str,context_chunks:List[Dict],model:str="gpt-4.1-mini", temperature:float=0.0)->str:
    prompt=build_prompt(question,context_chunks)
    response=client.responses.create(model=model,input=prompt,temperature=temperature)
    return response.output_text.strip()
