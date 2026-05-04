"""
SynapseOS — Self-Reflection Test
Tests reflect_and_refine() with good, vague, and hallucinated answers.
Run: python3 scripts/test_reflection.py
Requires: GROQ_API_KEY set (uses Groq 8b for judging)
"""
import asyncio
from src.cognitive.reflection import reflect_and_refine

CONTEXT = "SynapseOS uses Qdrant for vector storage. It uses Groq for LLM routing. It runs on Oracle ARM."


async def test_case(label, question, answer, expect_retry, min_faithfulness=None):
    print(f"\n=== {label} ===")
    final_answer, scores = await reflect_and_refine(
        question=question, context=CONTEXT, answer=answer,
    )
    combined = scores.get("combined", 0)
    faithfulness = scores.get("faithfulness", 0)
    relevancy = scores.get("relevancy", 0)
    completeness = scores.get("completeness", 0)
    retry_triggered = combined < 0.7

    print(f"  Faithfulness: {faithfulness:.2f}")
    print(f"  Relevancy: {relevancy:.2f}")
    print(f"  Completeness: {completeness:.2f}")
    print(f"  Combined: {combined:.2f}")
    print(f"  Retry triggered: {'Yes' if retry_triggered else 'No'}")
    if retry_triggered:
        print(f"  Improved answer: {final_answer[:200]}...")
    else:
        print(f"  Original answer kept: {final_answer[:200]}...")

    # Validate expectations
    passed = True
    if expect_retry and not retry_triggered:
        passed = False
    if not expect_retry and retry_triggered:
        passed = False
    if min_faithfulness and faithfulness < min_faithfulness:
        passed = False

    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    return passed


async def main():
    print("=== SynapseOS — Reflection Test ===")

    results = []

    # Test A: Good answer — should NOT trigger retry
    results.append(await test_case(
        "Test A — Great answer",
        question="What does SynapseOS use for vector storage?",
        answer="SynapseOS uses Qdrant for vector storage.",
        expect_retry=False,
    ))

    # Test B: Vague answer — should trigger retry
    results.append(await test_case(
        "Test B — Vague answer",
        question="What does SynapseOS use?",
        answer="SynapseOS uses various advanced technologies.",
        expect_retry=True,
    ))

    # Test C: Hallucinated answer — should trigger retry
    results.append(await test_case(
        "Test C — Hallucinated answer",
        question="What LLM does SynapseOS use?",
        answer="SynapseOS uses OpenAI GPT-4 and Pinecone for storage.",
        expect_retry=True,
        min_faithfulness=0.5,
    ))

    print(f"\n=== Final: {sum(results)}/3 cases behaved correctly ===")


if __name__ == "__main__":
    asyncio.run(main())
