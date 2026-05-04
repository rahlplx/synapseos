"""
SynapseOS — Python SDK Test
Run: python3 scripts/test_sdk.py
Requires: pip install -e sdk/python/, API running at http://localhost:8000
"""
import asyncio
from synapseos import AsyncSynapseClient

BASE = "http://localhost:8000"

async def main():
    client = AsyncSynapseClient(base_url=BASE, api_key="test-key", tenant_id="test")
    results = []

    # Test 1: query() non-streaming
    print("=== Test 1: query() non-streaming ===")
    try:
        result = await client.query("what is Qdrant?")
        answer = result.answer[:200] if result.answer else ""
        print(f"  Answer: {answer}...")
        passed = bool(result.answer)
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    # Test 2: query_stream() streaming
    print("\n=== Test 2: query_stream() streaming ===")
    try:
        chunks = 0
        async for chunk in client.query_stream("explain BM25 in one sentence"):
            chunks += 1
        print(f"  Chunks received: {chunks}")
        passed = chunks >= 1
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    # Test 3: ingest() queuing
    print("\n=== Test 3: ingest() ===")
    try:
        job = await client.ingest(["https://python.org"])
        print(f"  Job ID: {job.job_id}")
        passed = bool(job.job_id)
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    # Test 4: feedback()
    print("\n=== Test 4: feedback() ===")
    try:
        await client.feedback("trace-test-123", rating=1)
        passed = True
    except Exception as e:
        print(f"  Error: {e}")
        passed = False
    results.append(passed)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")

    print(f"\n=== Final: {sum(results)}/4 tests passed ===")

if __name__ == "__main__":
    asyncio.run(main())
