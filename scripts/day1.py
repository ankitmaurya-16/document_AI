from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def basic_chat():
    user_input=input("You: ")
    
    response=client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role":"system",
                "content":"You are a spicy person"
            },
            {
              "role":"user",
              "content":user_input  
            }
        ]
        # input=user_input
    )
    print("LLM: ",response.output_text)

def temp_test(temp):
    prompt= "Hello, explain recursion in short"
    response=client.responses.create(
        model="gpt-4.1-mini",
        temperature=temp,
        input=prompt
        
    )
    print("LLM: ",response.output_text)

if __name__=="__main__":
    # basic_chat()
    for t in [0, 0.7, 1.2, 2]:
        temp_test(t)