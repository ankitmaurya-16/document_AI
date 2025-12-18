from openai import OpenAI
from dotenv import load_dotenv
import os
import tiktoken

MODEL = "gpt-4.1-mini"

INPUT_COST_PER_1K = 0.0004
OUTPUT_COST_PER_1K = 0.0016

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

encoding = tiktoken.encoding_for_model(MODEL)


def count_tokens(text: str) -> int:
    return len(encoding.encode(text))


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1000) * INPUT_COST_PER_1K
    output_cost = (output_tokens / 1000) * OUTPUT_COST_PER_1K
    return input_cost + output_cost


def run():
    user_input = input("You: ")

    system_prompt = "You are a calm, concise teaching assistant."

    input_text = system_prompt + user_input
    input_tokens = count_tokens(input_text)

    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
    )

    output_text = response.output_text
    output_tokens = count_tokens(output_text)

    total_cost = estimate_cost(input_tokens, output_tokens)

    print("\nLLM:", output_text)
    print("\n--- Metrics ---")
    print(f"Input tokens:  {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"Estimated cost: ${total_cost:.6f}")


if __name__ == "__main__":
    run()
