"""LLM-as-judge: score a generated answer against the gold answer 0-5 with a
strict rubric. Returns ``None`` on failure so the caller drops that row from the
judge-mean while keeping retrieval metrics.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from logging_config import get_logger

log = get_logger("evals.judge")


JUDGE_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You grade whether an assistant's answer matches a gold reference answer "
    "to a factual question. Score 0-5 using this rubric:\n"
    "  5 = fully correct and complete\n"
    "  4 = correct but missing a minor detail\n"
    "  3 = partially correct; key fact right but notable omissions\n"
    "  2 = mostly wrong but touches on the topic\n"
    "  1 = wrong but plausible\n"
    "  0 = irrelevant, contradictory, or admits no answer\n"
    "Return strict JSON: {\"score\": <int 0-5>, \"reason\": \"<one sentence>\"}."
)


def _extract_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def score_answer(question: str, gold: str, predicted: str) -> Optional[dict]:
    """Return ``{"score": int, "reason": str}`` or ``None`` on failure."""
    from rag.generate import _openai  # reuse the same client + retry policy

    user = (
        f"Question: {question}\n\n"
        f"Gold answer: {gold}\n\n"
        f"Model answer: {predicted}\n\n"
        "Respond with JSON only."
    )
    try:
        response = _openai().chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=120,
            timeout=30.0,
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("judge.openai_failed", error=str(e))
        return None

    parsed = _extract_json(text)
    if not parsed or "score" not in parsed:
        log.warning("judge.unparseable_response", raw=text[:200])
        return None
    try:
        score = int(parsed["score"])
    except (TypeError, ValueError):
        return None
    if not 0 <= score <= 5:
        return None
    return {"score": score, "reason": str(parsed.get("reason", ""))[:300]}
