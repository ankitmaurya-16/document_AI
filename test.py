from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response=client.responses.create(
    model="gpt-4.1-mini",
    input="Say hello in an interesting way"
)

print(response.output_text)