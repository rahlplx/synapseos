"""
L7 — Memory (mem0 + KeyDB session)
mem0 uses existing Qdrant (synapse_memory collection) + PostgreSQL — zero new infra.
z.ai glm-4.5-flash (FREE) used as mem0 LLM judge for memory extraction.
"""
import os
import json
from mem0 import Memory
import redis.asyncio as redis

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))

# mem0 config — uses existing stack infrastructure
mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": os.environ.get("QDRANT_HOST", "qdrant"),
            "port": 6333,
            "collection_name": "synapse_memory",
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "openai",  # mem0 uses OpenAI-compatible — point to z.ai
        "config": {
            "model": "glm-4.5-flash",            # FREE z.ai model
            "openai_base_url": "https://api.z.ai/api/paas/v4/",
            "api_key": os.environ.get("ZAI_API_KEY", ""),
        },
    },
    "embedder": {
        "provider": "fastembed",
        "config": {"model": "BAAI/bge-base-en-v1.5"},
    },
    "history_db_path": os.environ.get("DATABASE_URL", "").replace("+asyncpg", ""),
}

memory = Memory.from_config(mem0_config)


async def load_memories(user_id: str, tenant_id: str, query: str) -> str:
    """Recall relevant long-term facts for this query."""
    try:
        results = memory.search(query=query, user_id=f"{tenant_id}:{user_id}", limit=5)
        if not results.get("results"):
            return ""
        facts = [r["memory"] for r in results["results"]]
        return "Memory:\n" + "\n".join(f"- {f}" for f in facts)
    except Exception:
        return ""


async def write_memory(user_id: str, tenant_id: str, messages: list[dict]):
    """Extract and store important facts from this conversation turn."""
    try:
        memory.add(messages=messages, user_id=f"{tenant_id}:{user_id}", metadata={"tenant_id": tenant_id})
    except Exception:
        pass  # non-blocking — memory write failure must not break response


async def load_session(session_id: str, window: int = 10) -> list[dict]:
    """Load last N turns from KeyDB."""
    raw = await keydb.lrange(f"session:{session_id}", -(window * 2), -1)
    turns = []
    for i in range(0, len(raw) - 1, 2):
        turns.append({"role": raw[i].decode(), "content": raw[i + 1].decode()})
    return turns


async def append_session(session_id: str, role: str, content: str):
    """Append turn. Expires after 24h."""
    await keydb.rpush(f"session:{session_id}", role, content)
    await keydb.expire(f"session:{session_id}", 86400)
