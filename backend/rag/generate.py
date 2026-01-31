from typing import List, Dict
from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()
client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def build_prompt(question:str,context_chunks:List[Dict])->str:
    context_text="\n\n".join(f"[Source:{chunk['source']}]\n{chunk['text']}" for chunk in context_chunks)
    prompt = f"""
            You are a careful assistant.
            Answer the question using ONLY the context below.
            You may use multiple context chunks.
            Cite sources like: [Source: filename]
            If the answer is not contained in the context, say:
            "The document don't have enough information to answer this question."

            Context:
            {context_text}

            Question:
            {question}
            """.strip()
    return prompt

def generate_answer(question:str,context_chunks:List[Dict],model:str="gpt-4o-mini", temperature:float=0.0)->str:
    prompt=build_prompt(question,context_chunks)
    print(f"DEBUG generate_answer(): Prompt length: {len(prompt)} chars")
    print(f"DEBUG generate_answer(): Context chunks: {len(context_chunks)}")
    print(f"DEBUG generate_answer(): First chunk preview: {context_chunks[0]['text'][:100]}..." if context_chunks else "No chunks")
    answer=""
    try:
        response=client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=512
        )
        answer = response.choices[0].message.content.strip()
        print(f"DEBUG generate_answer(): Response received: {answer[:200]}...")
        return answer
    except Exception as e:
        print(f"ERROR generate_answer(): OpenAI API error: {e}")
        answer = "AI response temporarily unavailable (quota exceeded)."
        return answer