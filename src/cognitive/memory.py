"""
L7 — Memory (mem0 + KeyDB session)
mem0 uses Qdrant (synapse_memory collection) + PostgreSQL.
LLM judge = Groq Llama-8b (fast, free tier).
All mem0 calls wrapped with asyncio.wait_for() to prevent indefinite blocking.
"""
import asyncio
import logging

from src.core.config import (
    KEYDB_URL, QDRANT_URL, GROQ_API_KEY, DATABASE_DSN,
    COLLECTION_MEMORY,
)
from src.core.clients import get_keydb

logger = logging.getLogger(__name__)

# ─── mem0 Configuration ──────────────────────────────────────────────────────
_qdrant_host = QDRANT_URL.replace("http://", "").replace("https://", "").split(":")[0]
_qdrant_port = int(QDRANT_URL.replace("http://", "").replace("https://", "").split(":")[1].rstrip("/"))

mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": _qdrant_host,
            "port": _qdrant_port,
            "collection_name": COLLECTION_MEMORY,
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "groq",
        "config": {
            "model": "llama-3.1-8b-instant",
            "api_key": GROQ_API_KEY,
        },
    },
    "embedder": {
        "provider": "fastembed",
        "config": {"model": "BAAI/bge-base-en-v1.5"},
    },
    "history_db_path": DATABASE_DSN,
}

_memory = None
MEM0_TIMEOUT = 5  # seconds


def _get_memory():
    """Lazy-initialize mem0 Memory."""
    global _memory
    if _memory is None:
        from mem0 import Memory
        _memory = Memory.from_config(mem0_config)
    return _memory


async def load_memories(user_id: str, tenant_id: str, query: str) -> str:
    """Recall relevant long-term memories. Returns empty string on failure."""
    try:
        memory = _get_memory()
        results = await asyncio.wait_for(
            asyncio.to_thread(
                memory.search, query=query,
                user_id=f"{tenant_id}:{user_id}", limit=5,
            ),
            timeout=MEM0_TIMEOUT,
        )
        if not results.get("results"):
            return ""
        facts = [r["memory"] for r in results["results"]]
        return "Relevant memory:\n" + "\n".join(f"- {f}" for f in facts)
    except asyncio.TimeoutError:
        logger.warning(f"[non-critical] load_memories timed out after {MEM0_TIMEOUT}s for user={user_id}")
        return ""
    except Exception as e:
        logger.warning(f"[non-critical] load_memories failed: {type(e).__name__}: {e}")
        return ""


async def write_memory(user_id: str, tenant_id: str, messages: list[dict]):
    """Extract and store facts from this conversation turn. Never crashes."""
    try:
        memory = _get_memory()
        await asyncio.wait_for(
            asyncio.to_thread(
                memory.add, messages=messages,
                user_id=f"{tenant_id}:{user_id}",
                metadata={"tenant_id": tenant_id},
            ),
            timeout=MEM0_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[non-critical] write_memory timed out after {MEM0_TIMEOUT}s for user={user_id}")
    except Exception as e:
        logger.warning(f"[non-critical] write_memory failed for user={user_id}: {type(e).__name__}: {e}")


async def load_session(session_id: str, window: int = 10) -> list[dict]:
    """Load last N turns from KeyDB session cache. Auto-expires after 24h."""
    try:
        keydb = get_keydb()
        raw = await keydb.lrange(f"session:{session_id}", -(window * 2), -1)
        turns = []
        for i in range(0, len(raw) - 1, 2):
            turns.append({"role": raw[i].decode(), "content": raw[i + 1].decode()})
        return turns
    except Exception as e:
        logger.warning(f"[non-critical] load_session failed: {type(e).__name__}: {e}")
        return []


async def append_session(session_id: str, role: str, content: str):
    """Append turn to session window. Auto-expires after 24h."""
    try:
        keydb = get_keydb()
        await keydb.rpush(f"session:{session_id}", role, content)
        await keydb.expire(f"session:{session_id}", 86400)
    except Exception as e:
        logger.warning(f"[non-critical] append_session failed: {type(e).__name__}: {e}")
