"""
SynapseOS — Tool Executor Test
Tests all 4 built-in tools including safety checks.
Run: python3 scripts/test_tools.py
Requires: Qdrant with vectors, GROQ_API_KEY set
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")

import asyncio
from src.cognitive.tools import ToolExecutor


async def main():
    print("=== SynapseOS — Tool Executor Test ===\n")
    executor = ToolExecutor()
    results = []

    # Test 1: web_search
    print("=== Test 1: web_search ===")
    try:
        result = await executor.execute("web_search", {"query": "Qdrant vector database python"}, "test")
        print(f"  Result (first 300 chars): {result[:300]}...")
        passed = bool(result) and "Error" not in result[:10]
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    # Test 2: calculate (valid)
    print("\n=== Test 2: calculate (valid) ===")
    try:
        result = await executor.execute("calculate", {"expression": "(42 * 1.5) + 10"}, "test")
        print(f"  Result: {result}")
        passed = result == "73.0"
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    # Test 3: calculate (injection attempt)
    print("\n=== Test 3: calculate (injection attempt) ===")
    try:
        result = await executor.execute("calculate", {"expression": "__import__('os').system('ls')"}, "test")
        print(f"  Result: {result}")
        passed = "Error" in result and "unsafe" in result.lower()
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    # Test 4: retrieve_knowledge
    print("\n=== Test 4: retrieve_knowledge ===")
    try:
        result = await executor.execute("retrieve_knowledge", {"query": "HNSW graph indexing"}, "test")
        print(f"  Result (first 200 chars): {result[:200]}...")
        passed = bool(result) and "No relevant" not in result[:20]
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    print(f"\n=== Final: {sum(results)}/4 tool tests passed ===")


if __name__ == "__main__":
    asyncio.run(main())
