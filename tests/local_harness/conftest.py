"""
SynapseOS Local Test Harness — pytest conftest
Sets up all patches before tests, provides fixtures for in-memory services.
"""
import os
import asyncio
import pytest

from tests.local_harness.patches import (
    setup_env,
    get_qdrant_client,
    get_keydb_client,
    get_pg_pool,
    create_qdrant_collections,
    close_qdrant_client,
    close_pg_pool,
    apply_patches,
)


# ── Environment setup (before any module imports) ──────────────────────────────
setup_env()

# ── One-time async initialization (runs at conftest import time) ───────────────
_initialized = False


def _ensure_initialized():
    """Initialize all fake services and apply patches. Idempotent."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_qdrant_collections())
    loop.close()
    apply_patches()


_ensure_initialized()


@pytest.fixture
def qdrant_client():
    """Provide the in-memory Qdrant client for tests (sync fixture)."""
    return _get_qdrant_client_sync()


def _get_qdrant_client_sync():
    """Get the Qdrant client synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(get_qdrant_client())
    finally:
        loop.close()


@pytest.fixture
def keydb_client():
    """Provide the fakeredis client for tests."""
    return get_keydb_client()


@pytest.fixture
def pg_pool():
    """Provide the FakePGPool for tests (sync fixture, lazy init on first use)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(get_pg_pool())
    finally:
        loop.close()


@pytest.fixture
def tenant_id():
    """Default tenant ID for tests."""
    return "test-tenant-001"


@pytest.fixture
def sample_chunks():
    """Sample text chunks for ingestion tests."""
    return [
        "SynapseOS is a self-improving BYOK RAG platform with a cognitive engine. "
        "It supports hybrid retrieval using dense and sparse vectors.",
        "The ingestion pipeline uses Crawl4AI for web scraping and Docling for document parsing. "
        "Semantic chunking splits text into 512-token overlapping segments.",
        "Self-reflection uses a fast LLM to judge answer quality on relevancy, "
        "faithfulness, and completeness. Answers below threshold are refined.",
        "The cognitive engine classifies queries as simple, complex, or tool-based. "
        "Each type follows a different execution path.",
        "Built-in tools include retrieve_knowledge, web_search, calculate, and call_api. "
        "Tenants can also register custom HTTP endpoint tools.",
    ]
