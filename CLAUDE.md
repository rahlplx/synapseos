# SynapseOS — Claude Code Instructions

## What This Is
Self-improving BYOK RAG platform with cognitive engine.
Two endpoints: `/v1/query` (fast RAG) and `/v1/think` (cognitive: memory + reasoning + tools + reflection).

## Locked Stack — Never Suggest Alternatives
- **Runtime**: FastAPI 0.115 + Uvicorn, Python 3.11
- **Vectors**: Qdrant 1.13.5 — dense (768d) + sparse BM25, hybrid RRF, cross-encoder rerank
- **Embeddings**: fastembed BAAI/bge-base-en-v1.5 (768d, CPU-only, ONNX)
- **LLM**: LiteLLM → Groq primary → OpenRouter → Anthropic fallback (BYOK per tenant)
- **Memory**: mem0ai (Qdrant `synapse_memory` collection + PostgreSQL)
- **Scraping**: Crawl4AI (async, JS-rendered pages)
- **Parsing**: Docling (PDF/DOCX layout-aware → markdown)
- **Evaluation**: RAGAS 0.2.15 (reference-free)
- **Optimization**: DSPy 2.5.20 MIPROv2
- **Observability**: Langfuse v3 self-hosted
- **Cache/Queue**: KeyDB (Redis-compatible)
- **Storage**: MinIO (S3-compatible)
- **Edge**: Cloudflare Workers (scales to zero, KV cache)
- **Deploy**: Coolify on Oracle ARM A1 — 4 vCPU / 24GB RAM, **NO GPU**

## ARM CPU Rules — Hard Constraints
```
OMP_NUM_THREADS=4          # Always — ONNX thread control
batch_size=64              # Ingestion embedding batches
batch_size=16              # Query embedding (real-time)
rerank_k=15                # Max docs into cross-encoder (ARM timeout prevention)
Docling concurrency=1      # One PDF at a time (OOM prevention)
KeyDB: AOF only            # appendonly yes + save "" — NO RDB fork()
Qdrant: on_disk=True       # memmap_threshold_kb=50000
DOCLING_CPU_ONLY=1         # No GPU acceleration
```

## File Structure
```
src/api/          → FastAPI routes + middleware
src/core/         → retrieval.py, generation.py, ingestion.py
src/cognitive/    → engine.py, memory.py, tools.py, reflection.py, planner.py
src/worker/       → nightly_optimizer.py, ingestion_worker.py
sdk/python/       → AsyncSynapseClient
sdk/typescript/   → SynapseOSClient
mcp/              → FastMCP server
cloudflare/       → Cloudflare Workers edge proxy
config/           → qdrant.yaml, litellm.yaml, keydb.conf
docs/             → architecture.md, cognitive.md, api.md, devops.md, prd.md
```

## Code Rules
- All LLM calls via LiteLLM with Groq primary
- Never hardcode API keys — always `os.environ["KEY"]`
- Never import z.ai API in runtime code
- All async functions — FastAPI is fully async
- Fernet AES-256 for tenant BYOK key encryption
- tenant_id payload filter on ALL Qdrant queries (never cross-tenant)
- `synapse_knowledge` = RAG vectors, `synapse_memory` = mem0 memory
- Memory writes always `asyncio.create_task()` — never block response

## When Generating Code
- Always show complete files — no truncation, no ellipsis, no "# rest of code"
- Include all imports
- Add type hints
- Add docstrings for functions
- Test scripts go in `scripts/` directory

## Build Phase
Currently in Phase 1 — Core RAG.
See SESSIONS.md for day-by-day build order.
See AGENTS.md for session log.
