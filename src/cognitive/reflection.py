"""
L7 — Self-Reflection
Uses FREE z.ai glm-4.7-flash to judge answer quality.
Adds ~200ms. Max 1 retry cycle.
"""
import json
from src.core.generation import fast_complete

REFLECTION_PROMPT = """Judge this RAG answer strictly. Score 0.0-1.0 each.

Question: {question}
Context (first 1500 chars): {context}
Answer: {answer}

Reply JSON only: {{"relevancy": 0.0, "faithfulness": 0.0, "completeness": 0.0, "critique": "what is wrong or empty string if good"}}"""

RETRY_PROMPT = """Rewrite this answer fixing: {critique}

Question: {question}
Context: {context}
Improved answer:"""


async def reflect_and_refine(
    question: str,
    context: str,
    answer: str,
    threshold: float = 0.70,
    max_retries: int = 1,
) -> tuple[str, dict]:
    for attempt in range(max_retries + 1):
        raw = await fast_complete(
            REFLECTION_PROMPT.format(
                question=question,
                context=context[:1500],
                answer=answer,
            ),
            max_tokens=200,
            json_mode=True,
        )
        try:
            scores = json.loads(raw)
        except Exception:
            return answer, {}

        combined = (
            0.4 * scores.get("faithfulness", 0.7)
            + 0.3 * scores.get("relevancy", 0.7)
            + 0.3 * scores.get("completeness", 0.7)
        )

        if combined >= threshold or attempt == max_retries:
            scores["combined"] = combined
            return answer, scores

        # Retry with critique
        answer = await fast_complete(
            RETRY_PROMPT.format(
                critique=scores.get("critique", "incomplete"),
                question=question,
                context=context,
            ),
            max_tokens=600,
        )

    return answer, {}
