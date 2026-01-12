from typing import List, Dict

MAX_CHARS_PER_CHUNK = 400


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def pack_context(
    chunks: List[Dict],
    max_chars_per_chunk: int = MAX_CHARS_PER_CHUNK
) -> str:

    sorted_chunks = sorted(
        chunks,
        key=lambda c: c["score"],
        reverse=True
    )

    packed_sections = []

    for i, chunk in enumerate(sorted_chunks, start=1):
        clean_text = truncate_text(
            chunk["text"],
            max_chars_per_chunk
        )

        section = f"""
--- SOURCE {i} ---
Source: {chunk['source']}
Similarity: {chunk['score']:.3f}

{clean_text}
""".strip()

        packed_sections.append(section)

    return "\n\n".join(packed_sections)

if __name__ == "__main__":
    from retrieve import retrieve

    query = "What is Retrieval-Augmented Generation?"

    chunks = retrieve(query)

    print("\n===== RAW DUMP =====\n")
    for c in chunks:
        print(c["text"][:200], "\n")

    print("\n===== CLEAN PACKED CONTEXT =====\n")
    packed = pack_context(chunks)
    print(packed)
