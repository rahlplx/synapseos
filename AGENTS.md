# AGENTS.md — SynapseOS Build Context

> This file is the single source of truth for any AI coding agent (Claude Code, Cursor, Windsurf, Cline, Kilo Code) working on this repo.
> Read this FIRST before touching any file. Update the Session Log at the bottom after every build session.

---

## What Is SynapseOS

Standalone BYOK RAG platform with cognitive engine. Integrates with any app via REST API, Python SDK, TypeScript SDK, or MCP server.

**Two endpoints:**
- `POST /v1/query` — fast hybrid RAG (~235ms, no memory)
- `POST /v1/think` — full cognitive engine (memory + multi-step reasoning + tool use + self-reflection, ~865ms)

---

## Locked Stack — Never Suggest Alternatives

| Component | Value |
|---|---|
| Runtime | FastAPI + Uvicorn |
| Vector DB | Qdrant 1.13.5+ |
| Embeddings | fastembed BAAI/bge-base-en-v1.5 (768d) |
| LLM Router | LiteLLM (Groq → OpenRouter → Anthropic fallback) |
| LLM Provider | z.ai GLM models (OpenAI-compatible, base_url=https://api.z.ai/api/paas/v4/) |
| Cache + Queue | KeyDB (Redis-compatible) |
| Object Store | MinIO |
| Memory | mem0ai (Qdrant + PostgreSQL backend) |
| Scraper | Crawl4AI |
| Parser | Docling |
| Evaluator | RAGAS 0.2.15 |
| Optimizer | DSPy 2.5.20+ MIPROv2 |
| Observability | Langfuse v3 self-hosted |
| Edge | Cloudflare Workers |
| Deploy | Coolify on Oracle ARM (4 vCPU / 24GB RAM, no GPU) |
| MCP | FastMCP 2.2.9+ |

**z.ai SDK usage:**
```python
# Always use z.ai SDK where possible
from zai import ZaiClient
client = ZaiClient(api_key=os.environ["ZAI_API_KEY"])

# Or via LiteLLM (OpenAI-compatible)
from litellm import acompletion
response = await acompletion(
    model="openai/glm-4.7-flash",           # FREE model
    api_base="https://api.z.ai/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
    messages=[...]
)
```

**z.ai free models to prefer:**
- `glm-4.7-flash` — FREE, use for classification + reflection
- `glm-4.5-flash` — FREE, use for memory extraction (mem0 judge)
- `glm-5.1` — paid flagship, use for complex generation only

---

## Project Architecture — 7 Layers

```
L1 Ingest: Crawl4AI → Docling → SemanticChunker → SHA256 dedup → fastembed → Qdrant + MinIO + PG
L2 Retrieval: Dense (768d) + BM25 sparse → RRF fusion → cross-encoder rerank → top 5
L3 Generation: LiteLLM → z.ai/Groq/OpenRouter/Anthropic fallback → SSE streaming
L4 Intelligence: RAGAS nightly → SFT/DPO JSONL → DSPy MIPROv2 prompt optimizer
L5 Integration: REST API + Python SDK + TypeScript SDK + FastMCP
L6 Edge: Cloudflare Workers (SHA-256 KV cache, scales-to-zero)
L7 Cognitive: mem0 memory + DSPy ReAct reasoning + Tool executor + Self-reflection
```

---

## File Structure

```
synapseos/
├── AGENTS.md                    ← THIS FILE — read first
├── README.md
├── .gitignore
├── .env.example                 ← copy to .env, fill values
├── docker-compose.yml           ← full stack
├── requirements.txt
├── pyproject.toml
│
├── docs/
│   ├── architecture.md          ← full technical spec (L1-L6)
│   ├── cognitive.md             ← L7 cognitive engine spec
│   ├── prd.md                   ← product requirements
│   ├── api.md                   ← API reference
│   └── devops.md                ← deployment guide
│
├── src/
│   ├── api/
│   │   ├── main.py              ← FastAPI app entry point
│   │   ├── middleware/
│   │   │   ├── tenant.py        ← TenantMiddleware (rate limit + BYOK inject)
│   │   │   └── langfuse_mw.py   ← Langfuse trace middleware
│   │   └── routes/
│   │       ├── query.py         ← POST /v1/query
│   │       ├── think.py         ← POST /v1/think (cognitive)
│   │       ├── ingest.py        ← POST /v1/ingest, GET /v1/ingest/{job_id}
│   │       ├── feedback.py      ← POST /v1/feedback
│   │       └── collections.py   ← GET /v1/collections, DELETE /v1/documents/{id}
│   │
│   ├── core/
│   │   ├── retrieval.py         ← hybrid_query (dense+BM25+RRF+rerank)
│   │   ├── generation.py        ← generate() via LiteLLM z.ai routing
│   │   └── ingestion.py         ← scrape + parse + chunk + embed + upsert
│   │
│   ├── cognitive/
│   │   ├── engine.py            ← cognitive_query() orchestrator
│   │   ├── memory.py            ← mem0 long-term + KeyDB session memory
│   │   ├── tools.py             ← ToolRegistry + ToolExecutor (4 built-ins)
│   │   ├── reflection.py        ← reflect_and_refine() inline judge
│   │   └── planner.py           ← classify_query() + SynapseReAct (DSPy)
│   │
│   └── worker/
│       ├── ingestion_worker.py  ← KeyDB job queue consumer
│       └── nightly_optimizer.py ← APScheduler: RAGAS → DSPy MIPROv2
│
├── sdk/
│   ├── python/
│   │   ├── synapseos/
│   │   │   ├── __init__.py
│   │   │   └── client.py        ← AsyncSynapseClient
│   │   └── pyproject.toml
│   └── typescript/
│       ├── src/
│       │   └── index.ts         ← SynapseOSClient (SvelteKit-compatible)
│       └── package.json
│
├── mcp/
│   └── synapse_mcp.py           ← FastMCP server (Claude Code/Cursor/Windsurf)
│
├── cloudflare/
│   └── worker.ts                ← Edge proxy + KV cache
│
├── config/
│   ├── qdrant.yaml              ← ARM mmap config
│   ├── litellm.yaml             ← z.ai + Groq + OpenRouter + Anthropic routes
│   └── keydb.conf               ← AOF, no RDB, 1.5GB cap
│
└── scripts/
    ├── init-db.sql              ← PostgreSQL schema
    ├── init-minio.sh            ← MinIO bucket setup
    └── healthcheck.sh           ← verify all services green
```

---

## Build Order (Phase 1 → Phase 3)

### Phase 1 — Core RAG (Hrittik builds first)
```
Week 1: Docker Compose up → all services healthy
Week 2: L1 Ingest working (Crawl4AI + Docling + fastembed → Qdrant)
Week 3: L2 Retrieval working (hybrid query endpoint live)
Week 4: L3 Generation working (/v1/query with z.ai streaming)
```

### Phase 2 — SDK + MCP
```
Week 5: Python SDK published, TypeScript SDK published
Week 6: FastMCP server live (Claude Code + Cursor plugged in)
Week 7: Cloudflare Workers edge deployed
```

### Phase 3 — Cognitive Engine
```
Week 8:  mem0 memory (session + long-term)
Week 9:  Self-reflection (reflect_and_refine)
Week 10: Tool registry + executor
Week 11: DSPy ReAct planner + full /v1/think endpoint
```

---

## Critical Rules for Agents

1. **Never commit `.env`** — only `.env.example` with placeholder values
2. **Never commit API keys** — all keys via environment variables
3. **OMP_NUM_THREADS=4** always set for ONNX models on ARM
4. **Docling worker concurrency = 1** — prevents OOM on 24GB ARM
5. **Qdrant batch_size=64** ingestion, **16** real-time query
6. **Cross-encoder input cap = 15 docs** — 30+ causes ARM timeout
7. **KeyDB: AOF only, no RDB** — fork() causes OOM
8. **Use z.ai glm-4.7-flash (FREE) for** classification, reflection, mem0 judge
9. **Use z.ai glm-5.1 for** complex generation (only when BYOK key available)
10. **mem0 collection name = `synapse_memory`** (separate from `synapse_knowledge`)

---

## z.ai SDK Integration Patterns

### LiteLLM config for z.ai (add to litellm.yaml)
```yaml
model_list:
  - model_name: "zai-flash"
    litellm_params:
      model: "openai/glm-4.7-flash"
      api_base: "https://api.z.ai/api/paas/v4/"
      api_key: "os.environ/ZAI_API_KEY"
  - model_name: "zai-flagship"
    litellm_params:
      model: "openai/glm-5.1"
      api_base: "https://api.z.ai/api/paas/v4/"
      api_key: "os.environ/ZAI_API_KEY"
```

### Direct z.ai SDK (async)
```python
import asyncio
from zai import AsyncZaiClient

async def zai_complete(prompt: str, model: str = "glm-4.7-flash") -> str:
    client = AsyncZaiClient(api_key=os.environ["ZAI_API_KEY"])
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
```

---

## Session Memory Log

> Agents: append your session summary here after every build session.
> Format: `## Session YYYY-MM-DD — What was built`

## Session 2026-05-04 — Initial repo scaffold
- Created full directory structure
- Added all 5 docs (architecture, prd, api, devops, cognitive)
- Added AGENTS.md, README, .gitignore, .env.example
- Added docker-compose.yml, config files, scripts
- Added src/ skeleton (all modules stubbed)
- Added SDK stubs (Python + TypeScript)
- Added MCP server, Cloudflare Worker
- Status: Scaffold complete. Phase 1 build ready for Hrittik.
- Next: `docker compose up` → verify all services → start L1 ingest
