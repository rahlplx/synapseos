"""
SynapseOS — /v1/query Endpoint Test
Tests the FastAPI endpoint with httpx.
Run: python3 scripts/test_endpoint.py
Requires: API running at http://localhost:8000
"""
import asyncio
import httpx
import time
import json


BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "test", "Content-Type": "application/json"}


async def test_non_streaming():
    """Test POST /v1/query with stream=false."""
    print("=== Test: Non-streaming /v1/query ===")
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BASE}/v1/query",
            headers=HEADERS,
            json={"question": "What is Qdrant?", "stream": False},
        )
    latency_ms = int((time.perf_counter() - start) * 1000)

    print(f"  Status: {resp.status_code}")
    print(f"  Latency: {latency_ms}ms")

    if resp.status_code != 200:
        print(f"  ❌ FAIL — Unexpected status code")
        print(f"  Response: {resp.text[:500]}")
        return False

    data = resp.json()
    answer = data.get("answer", "")
    sources = data.get("sources", [])
    trace_id = data.get("trace_id", "")

    print(f"  Answer: {answer[:200]}...")
    print(f"  Sources: {len(sources)}")
    print(f"  Trace ID: {trace_id}")

    passed = bool(answer) and resp.status_code == 200
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    return passed


async def test_streaming():
    """Test POST /v1/query with stream=true."""
    print("\n=== Test: Streaming /v1/query ===")
    start = time.perf_counter()
    chunks_received = 0
    full_answer = ""

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{BASE}/v1/query",
            headers=HEADERS,
            json={"question": "Explain HNSW indexing in one sentence", "stream": True},
        ) as resp:
            print(f"  Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"  ❌ FAIL — Unexpected status code")
                return False

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    payload = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if "chunk" in payload:
                    chunks_received += 1
                    full_answer += payload["chunk"]
                if payload.get("done"):
                    break

    latency_ms = int((time.perf_counter() - start) * 1000)
    print(f"  Chunks received: {chunks_received}")
    print(f"  Full answer: {full_answer[:200]}...")
    print(f"  Latency: {latency_ms}ms")

    passed = chunks_received >= 1 and bool(full_answer)
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    return passed


async def test_health():
    """Test GET /health (no auth required)."""
    print("\n=== Test: Health Check ===")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE}/health")
    print(f"  Status: {resp.status_code}")
    data = resp.json()
    print(f"  Response: {data}")
    passed = resp.status_code == 200 and data.get("status") == "ok"
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    return passed


async def main():
    print("=== SynapseOS — Endpoint Tests ===\n")
    results = []
    results.append(await test_health())
    results.append(await test_non_streaming())
    results.append(await test_streaming())
    print(f"\n=== Final: {sum(results)}/{len(results)} tests passed ===")


if __name__ == "__main__":
    asyncio.run(main())
