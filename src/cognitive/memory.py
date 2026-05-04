"""
L7 — Memory (mem0 + KeyDB session)
mem0 uses Qdrant (synapse_memory collection) + PostgreSQL.
LLM judge = Groq Llama-8b (fast, free tier) — NOT z.ai API.
"""
import os
import logging
import redis.asyncio as redis

logger = logging.getLogger(__name__)

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))

# ─── mem0 Configuration ──────────────────────────────────────────────────────
# Uses existing Qdrant + PostgreSQL infrastructure — no new services needed
mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": os.environ.get("QDRANT_HOST", "qdrant"),
            "port": 6333,
            "collection_name": "synapse_memory",  # Separate from synapse_knowledge
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "groq",  # NOT z.ai — uses Groq free tier
        "config": {
            "model": "llama-3.1-8b-instant",
            "api_key": os.environ.get("GROQ_API_KEY", ""),
        },
    },
    "embedder": {
        "provider": "fastembed",
        "config": {
            "model": "BAAI/bge-base-en-v1.5",
        },
    },
    "history_db_path": os.environ.get("DATABASE_URL", "").replace("+asyncpg", ""),
}

# Lazy init — only create Memory instance when first needed
_memory = None


def _get_memory():
    """Lazy-initialize mem0 Memory to avoid startup import issues."""
    global _memory
    if _memory is None:
        from mem0 import Memory
        _memory = Memory.from_config(mem0_config)
    return _memory


async def load_memories(user_id: str, tenant_id: str, query: str) -> str:
    """Recall relevant long-term memories for this query.
    Returns empty string (not None) when no memories found.
    Never raises — errors are caught and logged silently.
    """
    try:
        memory = _get_memory()
        results = memory.search(
            query=query,
            user_id=f"{tenant_id}:{user_id}",
            limit=5,
        )
        if not results.get("results"):
            return ""
        facts = [r["memory"] for r in results["results"]]
        return "Relevant memory:\n" + "\n".join(f"- {f}" for f in facts)
    except Exception as e:
        logger.warning(f"[non-critical] load_memories failed: {type(e).__name__}: {e}")
        return ""


async def write_memory(user_id: str, tenant_id: str, messages: list[dict]):
    """Extract and store important facts from this conversation turn.
    Must NEVER block or crash the response — always wrapped in try/except.
    Called via asyncio.create_task() for non-blocking execution.
    """
    try:
        memory = _get_memory()
        memory.add(
            messages=messages,
            user_id=f"{tenant_id}:{user_id}",
            metadata={"tenant_id": tenant_id},
        )
    except Exception as e:
        logger.warning(f"[non-critical] write_memory failed for user={user_id}: {type(e).__name__}: {e}")


async def load_session(session_id: str, window: int = 10) -> list[dict]:
    """Load last N turns from KeyDB session cache.
    KeyDB stores alternating [role, content, role, content, ...] in a list.
    Auto-expires after 24h (set by append_session).
    """
    try:
        raw = await keydb.lrange(f"session:{session_id}", -(window * 2), -1)
        turns = []
        for i in range(0, len(raw) - 1, 2):
            turns.append({
                "role": raw[i].decode(),
                "content": raw[i + 1].decode(),
            })
        return turns
    except Exception as e:
        logger.warning(f"[non-critical] load_session failed: {type(e).__name__}: {e}")
        return []


async def append_session(session_id: str, role: str, content: str):
    """Append turn to session window. Auto-expires after 24h.
    Called via asyncio.create_task() for non-blocking execution.
    """
    try:
        await keydb.rpush(f"session:{session_id}", role, content)
        await keydb.expire(f"session:{session_id}", 86400)  # 24h TTL
    except Exception as e:
        logger.warning(f"[non-critical] append_session failed: {type(e).__name__}: {e}")
