"""
Centralized configuration — all environment variables in one place.
Replaces scattered os.environ.get() calls across 10+ files.
Fail-fast on missing required vars. ARM tuning centralized here.
"""
import os

# ─── ARM CPU Tuning (MUST be set before importing fastembed/sentence-transformers) ───
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("DOCLING_CPU_ONLY", "1")


# ─── Helper ─────────────────────────────────────────────────────────────────────
def _env(key: str, default: str = None, required: bool = False) -> str:
    """Get env var with optional fail-fast."""
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(f"Required env var {key} not set")
    return val


# ─── Infrastructure URLs ────────────────────────────────────────────────────────
QDRANT_URL: str = _env("QDRANT_URL", "http://qdrant:6333")
KEYDB_URL: str = _env("KEYDB_URL", "redis://keydb:6379")
DATABASE_URL: str = _env("DATABASE_URL", "postgresql+asyncpg://synapse:changeme@postgres:5432/synapseos")
DATABASE_DSN: str = DATABASE_URL.replace("+asyncpg", "")  # asyncpg-compatible DSN
MINIO_ENDPOINT: str = _env("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY: str = _env("MINIO_ACCESS_KEY", "synapseos")
MINIO_SECRET_KEY: str = _env("MINIO_SECRET_KEY", "changeme")
LANGFUSE_PUBLIC_KEY: str = _env("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = _env("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST: str = _env("LANGFUSE_HOST", "http://langfuse:3100")

# ─── CORS ───────────────────────────────────────────────────────────────────────
CORS_ORIGINS: str = _env("CORS_ORIGINS", "*")  # Comma-separated, e.g. "https://app.example.com,https://admin.example.com"

# ─── API Keys ───────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = _env("GROQ_API_KEY", "")
OPENROUTER_API_KEY: str = _env("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY", "")
ENCRYPTION_KEY: str = _env("ENCRYPTION_KEY", required=False)

# ─── Admin ──────────────────────────────────────────────────────────────────────
ADMIN_SECRET: str = _env("ADMIN_SECRET", "")  # Required for /admin/* endpoints. Empty = disabled.

# ─── Collection Names ──────────────────────────────────────────────────────────
COLLECTION_KNOWLEDGE: str = "synapse_knowledge"
COLLECTION_MEMORY: str = "synapse_memory"

# ─── MinIO Buckets ─────────────────────────────────────────────────────────────
MINIO_RAW_BUCKET: str = "synapse-raw"
MINIO_PARSED_BUCKET: str = "synapse-parsed"
MINIO_DATASET_BUCKET: str = "synapseos"

# ─── ARM Constants ─────────────────────────────────────────────────────────────
INGEST_BATCH_SIZE: int = 64    # batch_size=64 for ingestion
QUERY_BATCH_SIZE: int = 16    # batch_size=16 for query
PREFETCH_K: int = 30          # prefetch 30 via RRF per dense/sparse
RERANK_K: int = 15            # HARD LIMIT: feed top-15 to cross-encoder
DEFAULT_FINAL_K: int = 5      # return top-5 after reranking
SCROLL_DELAY: float = 1.5     # Crawl4AI scroll delay for full page render

# ─── CRAG / Self-RAG Thresholds ────────────────────────────────────────────────
CONFIDENCE_THRESHOLD: float = 0.35  # CRAG: low confidence if top score < this
RELEVANCE_GATE: float = 0.20        # Self-RAG: minimum cross-encoder score

# ─── Model Names ───────────────────────────────────────────────────────────────
GENERATION_MODEL: str = "groq/llama-3.1-70b-versatile"  # Primary: quality generation
FAST_MODEL: str = "groq/llama-3.1-8b-instant"            # Fast: classify + reflect

# ─── System Prompts ────────────────────────────────────────────────────────────
SYSTEM_PROMPT: str = (
    "You are a precise knowledge assistant. Answer ONLY from the provided context. "
    "If the context does not contain the answer, say so explicitly."
)
SYSTEM_PROMPT_STREAM: str = (
    "You are a precise knowledge assistant. Answer using only the provided context."
)
SYSTEM_PROMPT_TOOLS: str = (
    "You are a precise assistant with access to tools. "
    "Use tools when needed to find information. "
    "Base your final answer on retrieved context and tool results."
)
