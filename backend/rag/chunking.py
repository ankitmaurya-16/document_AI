"""Recursive character text splitting.

Splits on the highest-priority separator (paragraph → line → sentence → word)
that keeps chunks under ``chunk_size``, then greedily packs with overlap.
"""
from __future__ import annotations

from typing import Iterable, List

_DEFAULT_SEPARATORS: tuple[str, ...] = (
    "\n\n",
    "\n",
    ". ",
    "? ",
    "! ",
    "; ",
    ", ",
    " ",
    "",
)


def _split_on(text: str, separator: str) -> List[str]:
    if separator == "":
        return list(text)
    # Keep the separator attached to the left-hand piece to avoid orphaning it.
    parts = text.split(separator)
    out: list[str] = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            out.append(p + separator)
        else:
            out.append(p)
    return [p for p in out if p]


def _merge(splits: Iterable[str], chunk_size: int, overlap: int) -> List[str]:
    """Greedy packer: accumulate splits until reaching chunk_size, then emit."""
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for piece in splits:
        piece_len = len(piece)
        if buf_len + piece_len > chunk_size and buf:
            merged = "".join(buf).strip()
            if merged:
                chunks.append(merged)
            # Build overlap tail from buf.
            if overlap > 0:
                tail: list[str] = []
                tail_len = 0
                for p in reversed(buf):
                    if tail_len + len(p) > overlap:
                        break
                    tail.insert(0, p)
                    tail_len += len(p)
                buf = tail
                buf_len = tail_len
            else:
                buf = []
                buf_len = 0
        buf.append(piece)
        buf_len += piece_len

    if buf:
        merged = "".join(buf).strip()
        if merged:
            chunks.append(merged)
    return chunks


def recursive_split(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    separators: tuple[str, ...] = _DEFAULT_SEPARATORS,
) -> List[str]:
    text = text or ""
    if len(text) <= chunk_size:
        stripped = text.strip()
        return [stripped] if stripped else []

    # Find the highest-priority separator present.
    for i, sep in enumerate(separators):
        if sep and sep in text:
            pieces = _split_on(text, sep)
            # Any piece still too big? Recurse on those with the rest of the list.
            out: list[str] = []
            for p in pieces:
                if len(p) <= chunk_size:
                    out.append(p)
                else:
                    out.extend(
                        recursive_split(
                            p,
                            chunk_size=chunk_size,
                            overlap=overlap,
                            separators=separators[i + 1 :],
                        )
                    )
            return _merge(out, chunk_size, overlap)

    # Fall-through: hard-split by character.
    return _merge(_split_on(text, ""), chunk_size, overlap)
