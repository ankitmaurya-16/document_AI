import argparse
import os
import sys

os.environ["TOKENIZERS_PARALLELISM"] = "false"

from ingest import ingest
from retrieve import retrieve
from generate import generate_answer


def run_ingest():
    ingest()


def run_query(question: str, top_k: int, show_sources: bool):
    if not question or not question.strip():
        print("\nPlease enter a non-empty question.\n")
        return

    chunks = retrieve(question, top_k=top_k)

    if not chunks:
        print("\nNo relevant context found.\n")
        return

    answer = generate_answer(question, chunks)

    print("\nAnswer:\n")
    print(answer)

    if show_sources:
        print("\nSources:\n")
        for i, c in enumerate(chunks, start=1):
            print(f"[{i}] {c['source']}")
        print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="RAG CLI — Retrieval-Augmented Generation"
    )

    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest documents and rebuild the index"
    )

    parser.add_argument(
        "--question",
        type=str,
        help="Question to ask using RAG"
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve (default: 5)"
    )

    parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Show retrieved context chunks"
    )

    args = parser.parse_args()

    if args.ingest:
        run_ingest()
        sys.exit(0)

    if args.question is not None:
        run_query(
            question=args.question,
            top_k=args.top_k,
            show_sources=args.show_sources
        )
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()
