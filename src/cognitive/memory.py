"""
L7 — Memory (mem0 + KeyDB session)
mem0 uses Qdrant (synapse_memory collection) + PostgreSQL.
LLM judge = Groq Llama-8b (fast, free tier) — NOT z.ai API.
"""
import os
from mem0 import Memory
import redis.asyncio as redis

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))

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
        "provider": "groq",
        "config": {
            "model": "llama-3.1-8b-instant",
            "api_key": os.environ.get("GROQ_API_KEY", ""),
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
    try:
        results = memory.search(query=query, user_id=f"{tenant_id}:{user_id}", limit=5)
        if not results.get("results"):
            return ""
        facts = [r["memory"] for r in results["results"]]
        return "Memory:\n" + "\n".join(f"- {f}" for f in facts)
    except Exception:
        return ""


async def write_memory(user_id: str, tenant_id: str, messages: list[dict]):
    try:
        memory.add(messages=messages, user_id=f"{tenant_id}:{user_id}", metadata={"tenant_id": tenant_id})
    except Exception:
        pass


async def load_session(session_id: str, window: int = 10) -> list[dict]:
    raw = await keydb.lrange(f"session:{session_id}", -(window * 2), -1)
    turns = []
    for i in range(0, len(raw) - 1, 2):
        turns.append({"role": raw[i].decode(), "content": raw[i + 1].decode()})
    return turns


async def append_session(session_id: str, role: str, content: str):
    await keydb.rpush(f"session:{session_id}", role, content)
    await keydb.expire(f"session:{session_id}", 86400)
