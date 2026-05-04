"""
SynapseOS Local Test Harness — Patches
Provides patched versions of all external dependencies so tests run
WITHOUT Docker, PostgreSQL, Redis/KeyDB, MinIO, or real LLM APIs.

All services are in-memory: Qdrant, fakeredis, aiosqlite, mock LLM.
"""
import os
import json
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

import aiosqlite
import fakeredis.aioredis
from qdrant_client import AsyncQdrantClient, models


# ─── Qdrant Patch ─────────────────────────────────────────────────────────────

_qdrant_client: Optional[AsyncQdrantClient] = None

COLLECTION_KNOWLEDGE = "synapse_knowledge"
COLLECTION_MEMORY = "synapse_memory"


async def get_qdrant_client() -> AsyncQdrantClient:
    """Return an in-memory AsyncQdrantClient (NOT connected to any server)."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(location=":memory:")
    return _qdrant_client


async def create_qdrant_collections():
    """Create synapse_knowledge and synapse_memory collections with proper vector configs."""
    client = await get_qdrant_client()
    for name in (COLLECTION_KNOWLEDGE, COLLECTION_MEMORY):
        if not await client.collection_exists(name):
            await client.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=768,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        modifier=models.Modifier.IDF
                    )
                },
                shard_number=1,
            )
            await client.create_payload_index(
                name, "tenant_id", models.PayloadSchemaType.KEYWORD
            )


async def close_qdrant_client():
    """Close the in-memory Qdrant client."""
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None


# ─── KeyDB / Redis Patch ──────────────────────────────────────────────────────

_keydb_client: Optional[fakeredis.aioredis.FakeRedis] = None


def get_keydb_client() -> fakeredis.aioredis.FakeRedis:
    """Return a fakeredis.aioredis.FakeRedis instance for async Redis operations."""
    global _keydb_client
    if _keydb_client is None:
        _keydb_client = fakeredis.aioredis.FakeRedis()
    return _keydb_client


# ─── PostgreSQL Patch (aiosqlite) ─────────────────────────────────────────────

_pg_db: Optional[aiosqlite.Connection] = None


async def get_pg_pool() -> "FakePGPool":
    """Return a FakePGPool wrapping an aiosqlite connection with the required tables."""
    global _pg_db
    if _pg_db is None:
        _pg_db = await aiosqlite.connect(":memory:")
        _pg_db.row_factory = aiosqlite.Row
        await _create_tables(_pg_db)
    return FakePGPool(_pg_db)


async def _create_tables(db: aiosqlite.Connection):
    """Create minimal SQLite tables matching init-db.sql schema."""
    await db.execute('''CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        org_name TEXT NOT NULL,
        tier TEXT DEFAULT 'starter',
        rpm_limit INTEGER DEFAULT 60,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        source_url TEXT,
        source_filename TEXT,
        minio_raw_path TEXT,
        minio_parsed_path TEXT,
        chunk_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS interaction_logs (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        query TEXT NOT NULL,
        answer TEXT NOT NULL,
        contexts TEXT NOT NULL,
        trace_id TEXT,
        ragas_faithfulness REAL,
        ragas_relevancy REAL,
        ragas_precision REAL,
        ragas_combined REAL,
        user_feedback INTEGER,
        dataset_exported INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS tools (
        id TEXT PRIMARY KEY,
        tenant_id TEXT REFERENCES tenants(id),
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        endpoint_url TEXT,
        method TEXT DEFAULT 'GET',
        auth_header BLOB,
        input_schema TEXT,
        is_builtin INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tenant_id, name)
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        tenant_id TEXT REFERENCES tenants(id),
        provider TEXT NOT NULL,
        encrypted_key BLOB NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS usage_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        event_type TEXT,
        quantity REAL,
        model TEXT,
        cost REAL,
        recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    await db.commit()


class FakePGConnection:
    """Wraps aiosqlite.Connection to match the asyncpg connection interface.

    Key differences handled:
    - asyncpg uses $1, $2 params; SQLite uses ?
    - asyncpg fetchrow returns a Record with dict-like access; aiosqlite returns Row
    - asyncpg execute returns status; aiosqlite returns cursor
    """

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @staticmethod
    def _convert_query(query: str) -> str:
        """Convert asyncpg-style $1,$2 params to SQLite ? placeholders."""
        import re
        return re.sub(r'\$\d+', '?', query)

    async def execute(self, query: str, *args):
        """Execute a query (INSERT, UPDATE, DELETE)."""
        q = self._convert_query(query)
        await self._db.execute(q, args)
        await self._db.commit()

    async def fetchrow(self, query: str, *args):
        """Fetch a single row. Returns a dict-like Row or None."""
        q = self._convert_query(query)
        cursor = await self._db.execute(q, args)
        row = await cursor.fetchone()
        if row is None:
            return None
        col_names = [d[0] for d in cursor.description]
        return dict(zip(col_names, row))

    async def fetch(self, query: str, *args):
        """Fetch all rows. Returns list of dict-like rows."""
        q = self._convert_query(query)
        cursor = await self._db.execute(q, args)
        rows = await cursor.fetchall()
        col_names = [d[0] for d in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

    async def fetchval(self, query: str, *args):
        """Fetch a single value."""
        q = self._convert_query(query)
        cursor = await self._db.execute(q, args)
        row = await cursor.fetchone()
        return row[0] if row else None

    async def close(self):
        """Close is a no-op when managed by the pool."""
        pass


class FakePGPool:
    """Mimics asyncpg.Pool interface with acquire() returning FakePGConnection."""

    def __init__(self, db: aiosqlite.Connection):
        self._conn = FakePGConnection(db)
        self._db = db

    @asynccontextmanager
    async def acquire(self):
        """Return the shared FakePGConnection."""
        yield self._conn

    async def close(self):
        """Close the underlying aiosqlite connection."""
        await self._db.close()


async def close_pg_pool():
    """Close the aiosqlite connection."""
    global _pg_db
    if _pg_db is not None:
        await _pg_db.close()
        _pg_db = None


# ─── MinIO Patch (no-op) ─────────────────────────────────────────────────────

class FakeMinioClient:
    """No-op MinIO client that simulates object storage."""

    def bucket_exists(self, bucket: str) -> bool:
        return True

    def make_bucket(self, bucket: str):
        pass

    def put_object(self, *args, **kwargs):
        pass

    def get_object(self, *args, **kwargs):
        return b""

    def list_objects(self, *args, **kwargs):
        return []

    def remove_object(self, *args, **kwargs):
        pass


def _get_minio():
    """Return a fake MinIO client."""
    return FakeMinioClient()


async def store_raw_to_minio(content: bytes, object_key: str) -> str:
    """No-op: just return the object key."""
    return object_key


async def store_parsed_to_minio(markdown: str, object_key: str) -> str:
    """No-op: just return the object key."""
    return object_key


# ─── LLM Mock ─────────────────────────────────────────────────────────────────

MOCK_ANSWER = "This is a mocked LLM answer based on the provided context."
MOCK_FAST_COMPLETE_JSON = json.dumps({
    "relevancy": 0.9,
    "faithfulness": 0.85,
    "completeness": 0.8,
    "critique": "",
})
MOCK_CLASSIFY_SIMPLE = "simple"
MOCK_CLASSIFY_COMPLEX = "complex"
MOCK_CLASSIFY_TOOL = "tool"


async def generate(
    question: str,
    contexts: list[str],
    tenant_api_key: str = None,
) -> str:
    """Mock generate() that returns a canned answer."""
    return MOCK_ANSWER


async def fast_complete(
    prompt: str,
    max_tokens: int = 300,
    json_mode: bool = False,
) -> str:
    """Mock fast_complete() that returns JSON for reflection or text for classify."""
    if "Score each criterion" in prompt or "Evaluate" in prompt:
        return MOCK_FAST_COMPLETE_JSON
    if "Classify" in prompt:
        return MOCK_CLASSIFY_SIMPLE
    if "Rewrite" in prompt:
        return "This is a refined answer addressing the critique with more detail."
    return "Mock fast completion response."


async def generate_stream(
    question: str,
    contexts: list[str],
    tenant_api_key: str = None,
    sources: list[dict] = None,
):
    """Mock generate_stream() that yields SSE chunks."""
    # Yield answer in a few chunks
    words = MOCK_ANSWER.split()
    for i, word in enumerate(words):
        chunk_text = word if i == 0 else " " + word
        yield f'data: {json.dumps({"chunk": chunk_text})}\n\n'
    # Final done message
    done_payload = {"done": True}
    if sources:
        done_payload["sources"] = sources
    yield f'data: {json.dumps(done_payload)}\n\n'


async def generate_with_tools(
    question: str,
    context: str,
    available_tools: list[dict],
    tenant_api_key: str = None,
    tenant_id: str = "",
) -> tuple[str, list[str]]:
    """Mock generate_with_tools() that returns a response with tools_used."""
    return MOCK_ANSWER, ["retrieve_knowledge"]


async def generate_hyde(query: str) -> str:
    """Mock HyDE generation."""
    return f"{query}\n\nThis is a hypothetical document that would answer the query in detail."


# ─── Monkey-Patching ──────────────────────────────────────────────────────────

def apply_patches():
    """Apply all monkey-patches to the source modules.

    This replaces module-level clients (qdrant, keydb, _get_pg, etc.)
    with our fake versions so that the real code paths work with
    in-memory services.
    """
    import src.core.ingestion as ingestion_mod
    import src.core.retrieval as retrieval_mod
    import src.core.generation as generation_mod
    import src.cognitive.memory as memory_mod
    import src.cognitive.reflection as reflection_mod
    import src.cognitive.tools as tools_mod
    import src.cognitive.generation_tools as gen_tools_mod
    import src.api.middleware.tenant as tenant_mod
    import src.api.middleware.langfuse_mw as langfuse_mw_mod
    import src.api.routes.ingest as ingest_route_mod
    import src.api.routes.collections as collections_mod

    # ── Ingestion module patches ──
    ingestion_mod.qdrant = _get_sync_qdrant()
    ingestion_mod.keydb = get_keydb_client()
    ingestion_mod._get_minio = _get_minio
    ingestion_mod.store_raw_to_minio = store_raw_to_minio
    ingestion_mod.store_parsed_to_minio = store_parsed_to_minio
    ingestion_mod._get_pg = _fake_get_pg

    # ── Retrieval module patches ──
    retrieval_mod.qdrant = _get_sync_qdrant()

    # ── Generation module patches ──
    generation_mod.generate = generate
    generation_mod.fast_complete = fast_complete
    generation_mod.generate_stream = generate_stream
    generation_mod.generate_hyde = generate_hyde

    # ── Memory module patches ──
    memory_mod.keydb = get_keydb_client()
    memory_mod._get_memory = _fake_get_memory
    memory_mod.load_memories = _fake_load_memories
    memory_mod.write_memory = _fake_write_memory

    # ── Reflection module patches (already uses fast_complete from generation) ──
    # reflection_mod imports fast_complete from generation, which is already patched

    # ── Tools module patches ──
    # The _retrieve_knowledge method imports hybrid_query from retrieval at call time,
    # which is fine since retrieval.qdrant is patched.

    # ── Generation tools module patches ──
    gen_tools_mod.generate_with_tools = generate_with_tools

    # ── API middleware patches ──
    tenant_mod.keydb = get_keydb_client()
    # Patch cipher for Fernet - use a known key
    from cryptography.fernet import Fernet
    tenant_mod.cipher = Fernet(os.environ["ENCRYPTION_KEY"].encode())

    # ── Langfuse middleware patches ──
    # The installed Langfuse version doesn't support start_observation(trace_id=...)
    # Replace the LangfuseMiddleware with a safe no-op version
    langfuse_mw_mod.LangfuseMiddleware = FakeLangfuseMiddleware

    # ── API route patches ──
    ingest_route_mod.keydb = get_keydb_client()
    collections_mod.qdrant = _get_sync_qdrant()


def _get_sync_qdrant() -> AsyncQdrantClient:
    """Get the current in-memory Qdrant client (must be called after init)."""
    if _qdrant_client is None:
        raise RuntimeError("Qdrant client not initialized. Call create_qdrant_collections() first.")
    return _qdrant_client


async def _fake_get_pg():
    """Replacement for ingestion._get_pg() that returns our FakePGPool."""
    return await get_pg_pool()


def _fake_get_memory():
    """Replacement for memory._get_memory() that returns a fake Memory object."""
    return FakeMemory()


async def _fake_load_memories(user_id: str, tenant_id: str, query: str) -> str:
    """Fake load_memories — returns empty string (no memories stored)."""
    return ""


async def _fake_write_memory(user_id: str, tenant_id: str, messages: list[dict]):
    """Fake write_memory — no-op."""
    pass


class FakeMemory:
    """Fake mem0 Memory that doesn't connect to any service."""

    def search(self, query: str, user_id: str = "", limit: int = 5) -> dict:
        return {"results": []}

    def add(self, messages: list[dict], user_id: str = "", metadata: dict = None):
        pass


class FakeLangfuseMiddleware:
    """No-op Langfuse middleware that doesn't call any external service.
    Replaces the real LangfuseMiddleware which has API compatibility issues
    with the installed langfuse version.
    """

    def __init__(self, app, **kwargs):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


# ─── Environment Setup ────────────────────────────────────────────────────────

def setup_env():
    """Set environment variables required by SynapseOS modules."""
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("DOCLING_CPU_ONLY", "1")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    os.environ.setdefault("QDRANT_HOST", "localhost")
    os.environ.setdefault("KEYDB_URL", "redis://localhost:6379")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://synapse:changeme@postgres:5432/synapseos")
    os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
    os.environ.setdefault("MINIO_ACCESS_KEY", "synapseos")
    os.environ.setdefault("MINIO_SECRET_KEY", "changeme")
    os.environ.setdefault("MINIO_USER", "synapseos")
    os.environ.setdefault("MINIO_PASSWORD", "changeme")
    os.environ.setdefault("GROQ_API_KEY", "gsk_placeholder_not_real")
    os.environ.setdefault("ENCRYPTION_KEY", "46Z1dGGVq3_iHijlZn3m0FG1bfIQE9XuqVAerUmgFqQ=")
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "")
    os.environ.setdefault("LANGFUSE_SECRET_KEY", "")
    os.environ.setdefault("LANGFUSE_HOST", "http://localhost:3100")
