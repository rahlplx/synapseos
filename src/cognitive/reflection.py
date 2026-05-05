"""
L7 — Self-Reflection

Evaluates answer quality using Groq Llama-3.1-8b-instant (~200ms per evaluation).
If the combined score falls below the threshold, the answer is retried with
the critique injected into the prompt. Maximum 1 retry cycle to bound latency.

Combined score formula: 0.4 * faithfulness + 0.3 * relevancy + 0.3 * completeness
"""
import json
import logging
from src.core.generation import fast_complete

logger = logging.getLogger(__name__)

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
    """Evaluate answer quality and retry with critique if below threshold.

    Args:
        question: The original user question.
        context: Retrieved context used to generate the answer.
        answer: The generated answer to evaluate.
        threshold: Combined score threshold for acceptance (default 0.70).
        max_retries: Maximum number of retry cycles (default 1).

    Returns:
        Tuple of (final_answer, reflection_scores_dict).
        Never crashes — returns original answer on any error.
    """
    for attempt in range(max_retries + 1):
        try:
            raw = await fast_complete(
                REFLECTION_PROMPT.format(
                    question=question,
                    context=context[:1500],
                    answer=answer,
                ),
                max_tokens=200,
                json_mode=True,
            )
            scores = json.loads(raw)
        except Exception as e:
            logger.warning(f"[non-critical] Reflection score parse failed: {type(e).__name__}: {e}")
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
        except Exception as e:
            logger.warning(f"[non-critical] Reflection retry failed: {type(e).__name__}: {e}")
            return answer, scores

    return answer, {}
