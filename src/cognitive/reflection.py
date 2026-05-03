"""
L7 — Self-Reflection
Uses Groq Llama-3.1-8b-instant (fast, ~200ms) to judge answer quality.
Adds ~200ms. Max 1 retry cycle.
"""
import json
from src.core.generation import fast_complete

REFLECTION_PROMPT = """You are a strict answer quality judge. Evaluate this RAG answer.

Question: {question}
Context (first 1500 chars): {context}
Answer: {answer}

Score each criterion 0.0 to 1.0. Be harsh.
1. relevancy: Does the answer directly address the question?
2. faithfulness: Is every claim supported by the context? No hallucinations?
3. completeness: Is the answer complete or does it miss obvious parts?

Reply in JSON only:
{{"relevancy": 0.0, "faithfulness": 0.0, "completeness": 0.0, "critique": "what is wrong or empty string if good"}}"""

RETRY_PROMPT = """Your previous answer had issues: {critique}

Rewrite the answer addressing these issues. Be precise, grounded in context only.

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
    """Evaluate answer quality. Retry with critique if below threshold.

    Returns (final_answer, reflection_scores).
    Fast model (Groq Llama-8b) keeps reflection latency ~200ms.
    Never crashes — returns original answer on any error.
    """
    for attempt in range(max_retries + 1):
        try:
            raw = await fast_complete(
                REFLECTION_PROMPT.format(
                    question=question,
                    context=context[:1500],  # Cap context for speed
                    answer=answer,
                ),
                max_tokens=200,
                json_mode=True,
            )
            scores = json.loads(raw)
        except (json.JSONDecodeError, Exception):
            # Malformed JSON or other error — return original answer as-is
            return answer, {}

        # Combined score: 0.4*faithfulness + 0.3*relevancy + 0.3*completeness
        combined = (
            0.4 * scores.get("faithfulness", 0.7)
            + 0.3 * scores.get("relevancy", 0.7)
            + 0.3 * scores.get("completeness", 0.7)
        )
        scores["combined"] = combined

        if combined >= threshold or attempt == max_retries:
            return answer, scores

        # Retry with critique injected
        try:
            answer = await fast_complete(
                RETRY_PROMPT.format(
                    critique=scores.get("critique", "Answer was incomplete"),
                    question=question,
                    context=context,
                ),
                max_tokens=600,
            )
        except Exception:
            return answer, scores

    return answer, {}
