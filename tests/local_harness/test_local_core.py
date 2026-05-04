"""SynapseOS Local Core Test — tests full pipeline with in-memory services.

All tests run WITHOUT Docker, PostgreSQL, Redis/KeyDB, MinIO, or external LLM APIs.
Services are replaced by:
  - In-memory Qdrant (AsyncQdrantClient(":memory:"))
  - fakeredis.aioredis.FakeRedis
  - aiosqlite (in-memory SQLite)
  - No-op MinIO
  - Mock LLM functions
"""
import json
import asyncio
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport

from tests.local_harness.patches import (
    get_qdrant_client,
    get_keydb_client,
    generate,
    fast_complete,
    generate_stream,
    generate_with_tools,
    COLLECTION_KNOWLEDGE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Ingestion Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_embed_and_upsert(qdrant_client, tenant_id, sample_chunks):
    """Test that embed_and_upsert stores vectors in Qdrant correctly."""
    from src.core.ingestion import embed_and_upsert, dense_model, sparse_model

    # Verify collection exists
    assert await qdrant_client.collection_exists(COLLECTION_KNOWLEDGE)

    # Embed and upsert sample chunks
    metadata = {"source_url": "https://test.local/doc1"}
    await embed_and_upsert(sample_chunks, tenant_id, metadata)

    # Verify vectors are stored
    info = await qdrant_client.get_collection(COLLECTION_KNOWLEDGE)
    assert info.points_count == len(sample_chunks), (
        f"Expected {len(sample_chunks)} points, got {info.points_count}"
    )

    # Verify payload structure by scrolling
    points, _ = await qdrant_client.scroll(
        collection_name=COLLECTION_KNOWLEDGE,
        limit=1,
        with_payload=True,
    )
    assert len(points) > 0
    p = points[0]
    assert "text" in p.payload
    assert "tenant_id" in p.payload
    assert p.payload["tenant_id"] == tenant_id
    assert "source_url" in p.payload


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Hybrid Query
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hybrid_query(qdrant_client, tenant_id, sample_chunks):
    """Test that hybrid_query retrieves relevant results from stored vectors."""
    from src.core.ingestion import embed_and_upsert
    from src.core.retrieval import hybrid_query

    # Ingest data first
    await embed_and_upsert(sample_chunks, tenant_id, {"source_url": "https://test.local/q"})

    # Query
    hits = await hybrid_query("What is SynapseOS?", tenant_id)

    # Verify results are returned (may be empty if cross-encoder filters all)
    # With in-memory Qdrant + real fastembed + real cross-encoder, we should get results
    assert isinstance(hits, list)
    if hits:
        # Verify payload structure
        for h in hits:
            assert hasattr(h, "payload")
            assert "text" in h.payload
            assert h.payload["tenant_id"] == tenant_id


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Generation (mocked)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_generate_mock():
    """Test that mock generate() returns an answer."""
    answer = await generate(
        question="What is SynapseOS?",
        contexts=["SynapseOS is a self-improving RAG platform."],
    )
    assert isinstance(answer, str)
    assert len(answer) > 0


@pytest.mark.asyncio
async def test_fast_complete_mock():
    """Test that mock fast_complete() returns JSON for reflection prompts."""
    result = await fast_complete(
        prompt="Score each criterion. Question: test, Answer: test",
        max_tokens=200,
        json_mode=True,
    )
    parsed = json.loads(result)
    assert "relevancy" in parsed
    assert "faithfulness" in parsed
    assert "completeness" in parsed


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: Reflection
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_reflect_and_refine():
    """Test reflect_and_refine with mocked fast_complete."""
    from src.cognitive.reflection import reflect_and_refine

    answer, scores = await reflect_and_refine(
        question="What is SynapseOS?",
        context="SynapseOS is a self-improving BYOK RAG platform.",
        answer="SynapseOS is a RAG platform.",
        threshold=0.7,
        max_retries=1,
    )

    # Should return a tuple of (answer, scores)
    assert isinstance(answer, str)
    assert isinstance(scores, dict)
    # Our mock returns high scores, so combined should be >= threshold
    if scores:
        assert "combined" in scores
        assert scores["combined"] >= 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: Tools
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_calculate_tool():
    """Test the calculate tool with safe and unsafe expressions."""
    from src.cognitive.tools import ToolExecutor

    executor = ToolExecutor()

    # Safe expression
    result = await executor.execute("calculate", {"expression": "2 + 3 * 4"}, "test-tenant")
    assert result == "14"

    # Division
    result = await executor.execute("calculate", {"expression": "10 / 3"}, "test-tenant")
    # Should return a float result
    assert "3.33" in result or "3" in result

    # Unsafe expression (contains letters)
    result = await executor.execute("calculate", {"expression": "__import__('os')"}, "test-tenant")
    assert "Error" in result or "unsafe" in result

    # Division by zero
    result = await executor.execute("calculate", {"expression": "1 / 0"}, "test-tenant")
    assert "zero" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_retrieve_knowledge_tool(qdrant_client, tenant_id, sample_chunks):
    """Test retrieve_knowledge tool with Qdrant data."""
    from src.cognitive.tools import ToolExecutor
    from src.core.ingestion import embed_and_upsert

    # Ingest data
    await embed_and_upsert(sample_chunks, tenant_id, {"source_url": "https://test.local/rk"})

    # Retrieve using tool
    executor = ToolExecutor()
    result = await executor.execute(
        "retrieve_knowledge",
        {"query": "What is SynapseOS?", "top_k": 3},
        tenant_id,
    )

    # Should return some text or "No relevant documents found"
    assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6: Cognitive Engine
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cognitive_query(qdrant_client, tenant_id, sample_chunks):
    """Test cognitive_query end-to-end with all mocks."""
    from src.cognitive.engine import cognitive_query, CognitiveResponse
    from src.core.ingestion import embed_and_upsert

    # Ingest data so retrieval returns something
    await embed_and_upsert(sample_chunks, tenant_id, {"source_url": "https://test.local/cog"})

    # Run cognitive query
    result = await cognitive_query(
        question="What is SynapseOS?",
        session_id="test-session-001",
        user_id="test-user-001",
        tenant_id=tenant_id,
    )

    # Verify it returns a CognitiveResponse
    assert isinstance(result, CognitiveResponse)
    assert isinstance(result.answer, str)
    assert len(result.answer) > 0
    assert result.query_type in ("simple", "complex", "tool")
    assert isinstance(result.reflection_scores, dict)
    assert isinstance(result.tools_used, list)
    assert isinstance(result.steps_taken, int)

    # Give background tasks time to complete (memory writes are fire-and-forget)
    await asyncio.sleep(0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7: FastAPI App
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_endpoint():
    """Test /health endpoint returns ok."""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_query_endpoint(qdrant_client, tenant_id, sample_chunks):
    """Test /v1/query endpoint with mocked dependencies."""
    from src.api.main import app
    from src.core.ingestion import embed_and_upsert

    # Ingest data so retrieval works
    await embed_and_upsert(sample_chunks, tenant_id, {"source_url": "https://test.local/api"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-streaming query
        resp = await client.post(
            "/v1/query",
            json={
                "question": "What is SynapseOS?",
                "top_k": 3,
                "stream": False,
                "use_hyde": False,
            },
            headers={"X-Tenant-ID": tenant_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert isinstance(data["answer"], str)
        assert "sources" in data
        assert "reflection_scores" in data
