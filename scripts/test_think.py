"""
SynapseOS — Cognitive Engine Test
Tests /v1/think with simple retrieval, memory recall, and tool use.
Run: python3 scripts/test_think.py
Requires: API running at http://localhost:8000, vectors in Qdrant, mem0 memory set up
"""
import asyncio
import httpx
import json


BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "test", "Content-Type": "application/json"}


async def test_think(label, body, check_fn):
    print(f"\n=== {label} ===")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{BASE}/v1/think", headers=HEADERS, json=body)
        print(f"  Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ❌ FAIL — Status {resp.status_code}: {resp.text[:300]}")
            return False

        data = resp.json()
        print(f"  Query type: {data.get('query_type', '?')}")
        print(f"  Steps: {data.get('steps_taken', 0)}")
        print(f"  Memories recalled: {data.get('memories_recalled', 0)}")
        print(f"  Tools used: {data.get('tools_used', [])}")
        answer = data.get('answer', '')[:200]
        print(f"  Answer: {answer}...")

        passed = check_fn(data)
        print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
        return passed
    except Exception as e:
        print(f"  Error: {e}")
        return False


async def main():
    print("=== SynapseOS — Cognitive Engine Test ===")

    results = []

    # Test A: Simple retrieval
    results.append(await test_think(
        "Test A — Simple retrieval",
        body={"question": "What is HNSW graph indexing?", "session_id": "think-A", "user_id": "rahul"},
        check_fn=lambda d: d.get("query_type") == "simple" and bool(d.get("answer")),
    ))

    # Test B: Memory recall
    results.append(await test_think(
        "Test B — Memory recall",
        body={"question": "What is my name?", "session_id": "think-B", "user_id": "rahul"},
        check_fn=lambda d: d.get("memories_recalled", 0) > 0 or "Rahul" in d.get("answer", ""),
    ))

    # Test C: Tool use (web search)
    results.append(await test_think(
        "Test C — Tool use",
        body={"question": "Search the web for Qdrant latest release", "session_id": "think-C", "user_id": "rahul"},
        check_fn=lambda d: d.get("query_type") in ("tool", "simple") and bool(d.get("answer")),
    ))

    print(f"\n=== Final: {sum(results)}/3 cognitive tests passed ===")


if __name__ == "__main__":
    asyncio.run(main())
