import tiktoken

Model_Name="gpt-4.1-mini"
def count_tokens(text: str, model:str=Model_Name)->int:
    encoding=tiktoken.encoding_for_model(model)
    token=encoding.encode(text)
    return len(token)
def run_experiment(label:str,text:str):
    print(f"\n---{label}---")
    print(f"Text: {text}")
    print(f"Token count: {count_tokens(text)}")
    

if __name__ == "__main__":
    run_experiment(
        "Short English",
        "Hello world!"
    )

    run_experiment(
        "Long English",
        "Explain recursion as if I am a beginner, using a clear analogy and simple language."
    )

    run_experiment(
        "Python Code",
        """
        def factorial(n):
            if n == 0:
                return 1
            return n * factorial(n - 1)
        """
    )

    run_experiment(
        "Equivalent Prose",
        "A factorial function returns 1 when the input is zero; otherwise it multiplies the number by the factorial of the previous integer."
    )

    run_experiment(
        "Emojis",
        "🙂🙂🙂🔥🚀"
    )