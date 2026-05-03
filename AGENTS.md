# AGENTS.md — SynapseOS Build Context

> Read this completely before touching any code.
> Single source of truth for all AI coding agents.
> Append to Session Log after every build session.

---

## Project

SynapseOS — standalone self-improving BYOK RAG platform with cognitive engine.
Integrates via REST API, Python SDK, TypeScript SDK, or MCP server.

Repo: github.com/rahlplx/synapseos
Owner: Rahul Paul (non-technical founder)
Deploy: Oracle ARM A1 — 4 vCPU / 24GB RAM — Coolify — NO GPU

---

## Two Endpoints

POST /v1/query  → Fast RAG (~235ms): hybrid retrieve + generate + reflect
POST /v1/think  → Cognitive (~865ms): memory + reasoning + tools + reflect

---

## Locked Stack

FastAPI 0.115 | Qdrant 1.13.5 | fastembed BAAI/bge-base-en-v1.5 768d ONNX |
LiteLLM → Groq → OpenRouter → Anthropic | mem0ai | Crawl4AI | Docling |
RAGAS 0.2.15 | DSPy 2.5.20 | Langfuse v3 | KeyDB | MinIO | FastMCP 2.2.9 |
Cloudflare Workers | Coolify

---

## ARM CPU Rules

OMP_NUM_THREADS=4 before every fastembed import
batch_size=64 ingestion / 16 query embedding
cross-encoder input cap = 15 docs HARD LIMIT
KeyDB: appendonly yes + save "" (NO RDB — fork causes OOM)
Qdrant: on_disk=True, memmap_threshold_kb=50000
Docling: concurrency=1, DOCLING_CPU_ONLY=1

---

## Collections

synapse_knowledge = RAG document vectors (768d dense + BM25 sparse)
synapse_memory    = mem0 user memory vectors (768d dense)

---

## LLM Routing

Generation:  groq/llama-3.1-70b-versatile
Fast tasks:  groq/llama-3.1-8b-instant (classify, reflect, mem0 judge)
Fallback 1:  openrouter/meta-llama/llama-3.1-8b-instruct
Fallback 2:  anthropic/claude-haiku-4-5
BYOK:        tenant key injected by TenantMiddleware from PostgreSQL (Fernet AES-256)

---

## File Structure

src/api/main.py                 FastAPI app entry
src/api/middleware/tenant.py    Rate limit + BYOK inject (runs before every route)
src/api/middleware/langfuse_mw.py  Trace every request
src/api/routes/query.py         POST /v1/query
src/api/routes/think.py         POST /v1/think
src/api/routes/ingest.py        POST /v1/ingest
src/api/routes/feedback.py      POST /v1/feedback
src/api/routes/collections.py   GET /v1/collections
src/core/retrieval.py           hybrid_query — dense+BM25+RRF+rerank
src/core/generation.py          LiteLLM/Groq generation + fast_complete + HyDE
src/core/ingestion.py           Crawl4AI + Docling + chunk + embed + upsert
src/cognitive/engine.py         cognitive_query orchestrator
src/cognitive/memory.py         mem0 long-term + KeyDB session
src/cognitive/tools.py          ToolExecutor (retrieve/web_search/calculate/call_api)
src/cognitive/reflection.py     reflect_and_refine (Groq judge)
src/cognitive/planner.py        classify_query + SynapseReAct (DSPy)
src/worker/nightly_optimizer.py RAGAS score + DSPy MIPROv2 at 02:00 UTC
sdk/python/synapseos/client.py  AsyncSynapseClient
sdk/typescript/src/index.ts     SynapseOSClient
mcp/synapse_mcp.py              FastMCP server
cloudflare/worker.ts            Edge proxy + KV cache
cloudflare/wrangler.toml        Cloudflare deploy config
config/qdrant.yaml              ARM mmap config
config/litellm.yaml             LLM routing + semantic cache
config/keydb.conf               AOF config
scripts/init-db.sql             PostgreSQL schema
scripts/init-minio.sh           MinIO bucket setup
scripts/healthcheck.sh          Verify all services

---

## Agent Rules Files

CLAUDE.md               Claude Code
.cursorrules            Cursor (legacy)
.cursor/rules/          Cursor MDC (new format)
.windsurfrules          Windsurf
.clinerules             Cline / Kilo Code
.github/copilot-instructions.md  GitHub Copilot

---

## Do Not Do

Never suggest z.ai API in runtime code
Never use sync calls in async FastAPI routes
Never hardcode secrets
Never pass more than 15 docs to cross-encoder
Never run Docling with concurrency more than 1
Never query Qdrant without tenant_id filter
Never store BYOK keys in plaintext
Never use RDB snapshots in KeyDB (save "")
Never use Celery — use KeyDB + BackgroundTasks

---

## Build Phase Status

Phase 1 Core RAG (Days 1-4)
  Day 1: Docker services live
  Day 2: Qdrant + ingest
  Day 3: Hybrid query
  Day 4: /v1/query endpoint

Phase 2 SDK + Edge (Days 5-8)
  Day 5: Python SDK
  Day 6: TypeScript SDK + widget
  Day 7: MCP server
  Day 8: Cloudflare Workers

Phase 3 Cognitive (Days 9-12)
  Day 9: mem0 memory
  Day 10: Self-reflection
  Day 11: Tool executor
  Day 12: /v1/think complete

---

## Session Log

## Session 2026-05-04 — Initial scaffold
- Built: Complete repo, all docs, Docker, SDKs, MCP, configs
- Status: Scaffold complete
- Next: Day 1 — Docker services live
