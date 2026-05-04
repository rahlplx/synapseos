# SynapseOS — Architecture

> Version: 1.0.0 | Stack locked May 2026 | Oracle ARM · Coolify · Cloudflare

---

## Conflict Resolution Log

> *4 AI outputs merged. Decisions below override any single-source recommendation.*

| Conflict | Doc 1 | Doc 2 | Doc 3 | Doc 4 | **VERDICT** |
|---|---|---|---|---|---|
| Tenant isolation | collection-per-tenant | shared + filter | shared + filter | shared + filter | **Shared collection + payload filter. Promote high-traffic tenants to dedicated collections at 10k+ docs.** |
| Cross-encoder input cap | 20 | 15 | 15 | 30→5 | **Prefetch=30 via RRF, feed top-15 to cross-encoder, return top-5.** |
| Sparse model | Qdrant/bm25 | Qdrant/bm25 | SPLADE_PP | Qdrant/bm25 | **Qdrant/bm25. SPLADE too heavy for ARM CPU.** |
| RAGAS version | 0.2.15 | 0.1.21+ | unversioned | 0.2.15 | **ragas==0.2.15** |
| HyDE | absent | absent | basic | full | **Optional flag `use_hyde`. Default OFF for latency-sensitive paths.** |
| fastembed batch_size | 64 | 64 | 16 | 64 | **64 for ingestion, 16 for real-time query path.** |
| DPO/SFT schema | Alpaca | Alpaca | ChatML | ChatML | **ChatML. Required by Qwen3 + Unsloth.** |
| DSPy demos cap | 2 | — | 2 | 3 | **max_bootstrapped_demos=3, max_labeled_demos=3** |

---

## Stack Matrix

| Layer | Package | Version | Role |
|---|---|---|---|
| Vector DB | Qdrant | 1.13.5+ | Dense/sparse storage, HNSW mmap, RRF |
| Embeddings | fastembed | 0.4.2+ | ONNX CPU embedding (bge-base-en-v1.5) |
| LLM Router | LiteLLM | 1.82.9+ | BYOK proxy, semantic cache, fallback chain |
| Scraper | Crawl4AI | 0.4.3+ | Async JS scraping, sitemap, BFS crawl |
| Parser | Docling | 2.19.0+ | PDF/DOCX layout-aware → clean markdown |
| Evaluator | RAGAS | 0.2.15 | Reference-free RAG scoring |
| Optimizer | DSPy | 2.5.20+ | MIPROv2 prompt auto-optimization |
| Observability | Langfuse | v3.0+ | Self-hosted trace + dataset export |
| Cache/Queue | KeyDB | 6.3.4+ | Semantic cache, rate limit, job queue |
| Object Store | MinIO | RELEASE.2025 | Raw docs, parsed markdown, JSONL export |
| API Runtime | FastAPI | 0.115+ | Async API, ASGI middleware |
| MCP Server | FastMCP | 2.2.9+ | Claude Code / Cursor / Windsurf integration |
| Edge | Cloudflare Workers | — | Scales-to-zero proxy, KV cache |
| Deploy | Coolify | latest | Docker orchestration on Oracle ARM |

---

## System Architecture — 6 Layers

```
┌─────────────────────────────────────────────────────────────┐
│  EDGE LAYER — Cloudflare Workers                            │
│  SHA-256 exact cache → KV hit (<50ms) → Oracle bypass      │
│  Cache miss → forward to FastAPI backend                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  API LAYER — FastAPI (Oracle ARM 4 vCPU / 24GB)            │
│  TenantMiddleware → BYOKMiddleware → RateLimitMiddleware    │
│  → /v1/query  /v1/ingest  /v1/feedback  /v1/collections    │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼───────┐ ┌────────▼──────┐ ┌────────▼────────┐
│ RETRIEVAL     │ │ INGESTION     │ │ GENERATION      │
│ Dense embed   │ │ Crawl4AI      │ │ LiteLLM router  │
│ BM25 sparse   │ │ Docling       │ │ Groq primary    │
│ RRF fusion    │ │ Semantic chunk│ │ OpenRouter fb   │
│ Cross-encoder │ │ SHA-256 dedup │ │ Anthropic last  │
│ Langfuse trace│ │ KeyDB queue   │ │ SSE streaming   │
└───────┬───────┘ └────────┬──────┘ └────────┬────────┘
        │                  │                  │
┌───────▼──────────────────▼──────────────────▼────────┐
│  STORAGE LAYER                                        │
│  Qdrant (vectors) · PostgreSQL (meta) · MinIO (blobs)│
│  KeyDB (cache + jobs + rate limits + hashes)         │
└───────────────────────────┬───────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────┐
│  INTELLIGENCE LOOP — Nightly 02:00 UTC                │
│  RAGAS auto-score → SFT/DPO export → DSPy MIPROv2    │
│  → Optimized prompts deployed → feedback closed       │
└───────────────────────────────────────────────────────┘
```

---

## Layer 1 — Ingestion Engine

### Pipeline Flow

```
URL / File
    → Crawl4AI (web) or Docling (PDF/DOCX)
    → PruningContentFilter → fit_markdown
    → SemanticChunker (512 tokens, 64 overlap)
    → SHA-256 dedup check (KeyDB set)
    → fastembed batch embed (dense 768d + sparse BM25)
    → Qdrant upsert (dual vector)
    → MinIO archive (raw + parsed)
    → PostgreSQL metadata insert
    → Langfuse ingestion span
```

### Crawl4AI — JS-Rendered Scraping

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

async def scrape_url(url: str) -> str:
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.48)
    )
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_generator,
        page_timeout=30000,       # 30s hard timeout — prevents DOM hang
        scan_full_page=True,
        scroll_delay=1.5,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        return result.markdown.fit_markdown
```

**ARM gotcha**: Crawl4AI launches headless Chromium. On Oracle ARM, pin `playwright==1.49.0` and set `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright`. Chromium ARM64 binary ~180MB, RAM usage ~400MB per instance. Max 1 concurrent Chromium process on this budget.

### Docling — Layout-Aware Document Parsing

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()

def parse_document(file_path: str) -> str:
    doc = converter.convert(source=f"file://{file_path}")
    markdown = doc.export_to_markdown()
    return markdown
```

**ARM gotcha**: Docling uses vision models for layout detection. On CPU-only ARM, set `DOCLING_CPU_ONLY=1`. Processing a 100-page PDF takes ~90s and peaks at ~3.5GB RAM. Queue concurrency MUST be 1.

### Semantic Chunking + Dedup

```python
import hashlib
from semchunk import SemanticChunker

chunker = SemanticChunker(
    tokenizer="BAAI/bge-base-en-v1.5",
    chunk_size=512,
    overlap=64,
)

async def chunk_and_dedup(text: str, tenant_id: str) -> list[str]:
    chunks = chunker.chunk_text(text)
    unique = []
    for chunk in chunks:
        chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()
        added = await keydb.sadd(f"tenant:{tenant_id}:hashes", chunk_hash)
        if added:
            unique.append(chunk)
    return unique
```

### Dual Vector Ingest

```python
import os
os.environ["OMP_NUM_THREADS"] = "4"

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import AsyncQdrantClient, models

dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)

async def embed_and_upsert(
    chunks: list[str],
    metadata: list[dict],
    tenant_id: str,
):
    dense_vecs = list(dense_model.embed(chunks, batch_size=64))
    sparse_vecs = list(sparse_model.embed(chunks, batch_size=64))

    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector={
                "dense": dense_vecs[i].tolist(),
                "sparse": sparse_vecs[i].as_object(),
            },
            payload={"text": chunks[i], "tenant_id": tenant_id, **metadata[i]},
        )
        for i in range(len(chunks))
    ]
    await qdrant.upsert(collection_name="synapse_knowledge", points=points)
```

---

## Layer 2 — Retrieval Engine

### Qdrant Collection Schema

```python
client.create_collection(
    collection_name="synapse_knowledge",
    vectors_config={
        "dense": models.VectorParams(
            size=768,
            distance=models.Distance.COSINE,
            on_disk=True,                    # ARM mmap — critical
        )
    },
    sparse_vectors_config={
        "sparse": models.SparseVectorParams(
            modifier=models.Modifier.IDF     # BM25 IDF at index time
        )
    },
    shard_number=1,
    optimizers_config=models.OptimizersConfigDiff(
        memmap_threshold_kb=50_000,
        indexing_threshold_kb=100_000,
        max_segment_size_kb=65_536,
    ),
)

# Index tenant_id for O(log n) filter performance
client.create_payload_index(
    collection_name="synapse_knowledge",
    field_name="tenant_id",
    field_schema=models.PayloadSchemaType.KEYWORD,
)
```

### Hybrid Query — RRF + Cross-Encoder

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)

async def hybrid_query(
    query: str,
    tenant_id: str,
    prefetch_k: int = 30,
    rerank_k: int = 15,
    final_k: int = 5,
    use_hyde: bool = False,
):
    search_query = query
    if use_hyde:
        search_query = await generate_hyde(query)   # adds ~1000ms LLM latency

    dense_vec = next(dense_model.embed([search_query]))
    sparse_vec = next(sparse_model.embed([search_query]))

    tenant_filter = models.Filter(
        must=[models.FieldCondition(
            key="tenant_id",
            match=models.MatchValue(value=tenant_id)
        )]
    )

    hits = (await qdrant.query_points(
        collection_name="synapse_knowledge",
        prefetch=[
            models.Prefetch(query=dense_vec.tolist(), using="dense",
                            limit=prefetch_k, filter=tenant_filter),
            models.Prefetch(query=sparse_vec.as_object(), using="sparse",
                            limit=prefetch_k, filter=tenant_filter),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=rerank_k,
    )).points

    if not hits:
        return []

    pairs = [[query, h.payload["text"]] for h in hits]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)
    return [h for h, s in ranked[:final_k] if s > 0.1]
```

### Latency Budget (Oracle ARM 4 vCPU)

| Phase | Latency |
|---|---|
| Dense embed (query) | 12ms |
| BM25 sparse embed | 8ms |
| Qdrant prefetch×2 + RRF | 15ms |
| Cross-encoder top-15 | ~200ms |
| **Total (no HyDE)** | **~235ms P95** |
| HyDE generation (optional) | +800–1200ms |

**Cap rerank_k at 15.** At 30 docs cross-encoder = ~400ms. At 100 docs = ~2500ms (unacceptable).

---

## Layer 3 — Generation Engine

```python
from litellm import acompletion

FALLBACK_CHAIN = [
    {"model": "groq/llama-3.1-8b-instant"},
    {"model": "openrouter/meta-llama/llama-3.1-8b-instruct"},
    {"model": "anthropic/claude-haiku-4-5"},
]

async def generate(
    question: str,
    contexts: list[str],
    tenant_api_key: str,
    stream: bool = True,
):
    context_str = "\n\n---\n\n".join(contexts)
    system_prompt = (
        "You are a precise knowledge assistant. Answer ONLY from the provided context. "
        "If the context does not contain the answer, say so explicitly."
    )

    response = await acompletion(
        model=FALLBACK_CHAIN[0]["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        api_key=tenant_api_key,
        stream=stream,
        fallbacks=FALLBACK_CHAIN[1:],
        num_retries=1,
        request_timeout=30,
    )
    return response
```

### LiteLLM Semantic Cache (KeyDB)

```yaml
# litellm_config.yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: keydb
    port: 6379
    semantic_cache:
      enabled: true
      embedding_model: "BAAI/bge-base-en-v1.5"
      similarity_threshold: 0.92    # serves near-identical queries from cache
```

---

## Layer 4 — Self-Improvement Loop

### Interaction Logging Schema (PostgreSQL)

```sql
CREATE TABLE interaction_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    contexts JSONB NOT NULL,          -- array of retrieved chunk texts
    trace_id VARCHAR(128),            -- Langfuse trace ID
    ragas_faithfulness NUMERIC(4,3),
    ragas_relevancy NUMERIC(4,3),
    ragas_precision NUMERIC(4,3),
    ragas_combined NUMERIC(4,3),
    user_feedback SMALLINT,           -- +1 thumbs up, -1 down, NULL = none
    dataset_exported BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_logs_tenant_scored ON interaction_logs(tenant_id, ragas_combined)
    WHERE dataset_exported = FALSE;
```

### RAGAS Auto-Evaluation

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from datasets import Dataset

async def score_interaction(log: dict) -> dict:
    dataset = Dataset.from_list([{
        "question": log["query"],
        "answer": log["answer"],
        "contexts": log["contexts"],
    }])

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        # Judge LLM via LiteLLM — use different provider than generator to avoid bias
        # e.g. if generator=Groq/Llama, judge=GPT-4o-mini or Claude-Haiku
    )

    combined = (
        0.4 * result["faithfulness"] +
        0.3 * result["answer_relevancy"] +
        0.3 * result["context_precision"]
    )
    return {
        "faithfulness": result["faithfulness"],
        "answer_relevancy": result["answer_relevancy"],
        "context_precision": result["context_precision"],
        "combined": combined,
    }
```

### SFT + DPO Dataset Generator

```python
import boto3
import json
from io import BytesIO

async def export_datasets(db_pool, minio_client, version: str = "v1"):
    async with db_pool.acquire() as conn:
        # SFT: combined ≥ 0.7, all dimensions ≥ 0.6
        sft_rows = await conn.fetch("""
            SELECT query, answer FROM interaction_logs
            WHERE ragas_combined >= 0.7
              AND ragas_faithfulness >= 0.6
              AND ragas_relevancy >= 0.6
              AND dataset_exported = FALSE
        """)

        # DPO: pair best vs worst answer for same query
        dpo_rows = await conn.fetch("""
            SELECT DISTINCT ON (query)
                query,
                first_value(answer) OVER w AS chosen,
                last_value(answer) OVER w AS rejected
            FROM interaction_logs
            WHERE ragas_combined IS NOT NULL
            WINDOW w AS (PARTITION BY query ORDER BY ragas_combined
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            HAVING max(ragas_combined) >= 0.7 AND min(ragas_combined) <= 0.4
        """)

    # SFT — ChatML format (Qwen3 / Unsloth compatible)
    sft_lines = []
    for row in sft_rows:
        sft_lines.append(json.dumps({
            "messages": [
                {"role": "system", "content": "You are a precise knowledge assistant."},
                {"role": "user", "content": row["query"]},
                {"role": "assistant", "content": row["answer"]},
            ]
        }))

    # DPO — ChatML format
    dpo_lines = []
    for row in dpo_rows:
        dpo_lines.append(json.dumps({
            "prompt": [
                {"role": "system", "content": "You are a precise knowledge assistant."},
                {"role": "user", "content": row["query"]},
            ],
            "chosen": [{"role": "assistant", "content": row["chosen"]}],
            "rejected": [{"role": "assistant", "content": row["rejected"]}],
        }))

    # Upload to MinIO via streaming multipart
    for key, lines in [
        (f"datasets/{version}/sft_train.jsonl", sft_lines),
        (f"datasets/{version}/dpo_train.jsonl", dpo_lines),
    ]:
        data = "\n".join(lines).encode()
        minio_client.put_object(
            "synapseos",
            key,
            BytesIO(data),
            len(data),
            content_type="application/x-ndjson",
        )
```

### DSPy MIPROv2 Nightly Optimizer

```python
import dspy
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class SynapseRAG(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought("context, question -> answer")

    def forward(self, question, context):
        return self.generate(context=context, question=question)

async def run_nightly_optimization(gold_logs: list[dict]):
    trainset = [
        dspy.Example(
            question=log["query"],
            context="\n".join(log["contexts"]),
            answer=log["answer"],
        ).with_inputs("question", "context")
        for log in gold_logs
        if log["ragas_combined"] >= 0.85
    ]

    if len(trainset) < 10:
        return  # insufficient data — skip

    optimizer = dspy.MIPROv2(
        metric=dspy.evaluate.SemanticF1(),
        auto="light",
        num_threads=4,
        max_bootstrapped_demos=3,
        max_labeled_demos=3,
    )

    optimized = optimizer.compile(SynapseRAG(), trainset=trainset, num_trials=25)
    optimized.save("optimized_prompt.json")

scheduler = AsyncIOScheduler()
scheduler.add_job(run_nightly_optimization, "cron", hour=2, minute=0)
scheduler.start()
```

---

## Layer 5 — Integration Layer

### Multi-Tenant BYOK Middleware

```python
import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from cryptography.fernet import Fernet
import redis.asyncio as redis

keydb = redis.from_url("redis://keydb:6379")
cipher = Fernet(b"<ENV_SECRET_KEY_32_BYTES_BASE64>")

class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise HTTPException(401, "Missing X-Tenant-ID")

        # 1. Rate limit — sliding window — evaluated BEFORE any ONNX work
        window = int(time.time() // 60)
        limit_key = f"rate:{tenant_id}:{window}"
        count = await keydb.incr(limit_key)
        if count == 1:
            await keydb.expire(limit_key, 60)
        if count > 60:   # 60 RPM default; override per tier in DB
            raise HTTPException(429, "Rate limit exceeded")

        # 2. BYOK key injection — AES-256 Fernet decrypt
        encrypted_key = await db.fetchval(
            "SELECT encrypted_key FROM api_keys WHERE tenant_id=$1 AND active=TRUE",
            tenant_id
        )
        if not encrypted_key:
            raise HTTPException(403, "BYOK credentials not configured")

        request.state.tenant_id = tenant_id
        request.state.litellm_api_key = cipher.decrypt(encrypted_key).decode()

        return await call_next(request)
```

### PostgreSQL Schema (Multi-Tenant Core)

```sql
CREATE TABLE tenants (
    id VARCHAR(64) PRIMARY KEY,
    org_name VARCHAR(128) NOT NULL,
    tier VARCHAR(16) DEFAULT 'starter',   -- starter | growth | pro
    rpm_limit INTEGER DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) REFERENCES tenants(id),
    provider VARCHAR(32),                  -- groq | openrouter | anthropic
    encrypted_key BYTEA NOT NULL,          -- Fernet AES-256
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE usage_records (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(16),               -- query | ingest | token
    quantity NUMERIC,
    model VARCHAR(64),
    cost NUMERIC(10,6),
    recorded_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_usage ON usage_records(tenant_id, recorded_at DESC);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL,
    source_url TEXT,
    minio_raw_path TEXT,
    minio_parsed_path TEXT,
    chunk_count INTEGER,
    status VARCHAR(16) DEFAULT 'pending', -- pending | processing | done | failed
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Layer 6 — Observability

### Langfuse FastAPI Middleware

```python
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

langfuse = Langfuse(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="http://langfuse:3100",
)

@app.middleware("http")
async def langfuse_trace_middleware(request: Request, call_next):
    if "/query" not in request.url.path:
        return await call_next(request)

    trace = langfuse.trace(
        name="rag-query",
        metadata={"tenant": getattr(request.state, "tenant_id", "unknown")},
    )
    langfuse_context.configure(trace=trace)
    try:
        response = await call_next(request)
        trace.update(output={"status": response.status_code})
    finally:
        langfuse.flush()
    return response

# Attach RAGAS scores after evaluation
def attach_ragas_scores(trace_id: str, scores: dict):
    for name, value in scores.items():
        langfuse.score(trace_id=trace_id, name=name, value=value)
```

---

## RAM Budget — Oracle ARM 4 vCPU / 24GB

| Service | Idle | Peak | Coolify Cap |
|---|---|---|---|
| OS + Kernel | 1.0 GB | 2.5 GB | N/A |
| Qdrant (mmap) | 1.5 GB | 4.0 GB | `memory: 4G` |
| PostgreSQL | 0.5 GB | 2.0 GB | `memory: 2G` |
| KeyDB | 0.5 GB | 1.5 GB | `memory: 1.5G` |
| FastAPI + fastembed | 1.5 GB | 6.0 GB | `memory: 6G` |
| Docling worker | 0 (idle) | 4.5 GB | `memory: 4.5G` |
| LiteLLM proxy | 0.2 GB | 0.5 GB | `memory: 512M` |
| Langfuse | 1.0 GB | 2.5 GB | `memory: 2.5G` |
| MinIO | 0.5 GB | 1.0 GB | `memory: 1G` |
| **Total** | **~6.7 GB** | **~24.0 GB** | **Hard stop at 24GB** |

**Critical rule**: Docling worker concurrency = 1. Qdrant `QDRANT__STORAGE__PERFORMANCE__ASYNC_SCORER=true` (io_uring for ARM disk I/O).

---

## Production Hardening — Top 10 Failure Modes

| # | Failure | Detection | Mitigation |
|---|---|---|---|
| 1 | fastembed ONNX OOM | Coolify OOMKilled log | `batch_size=16` real-time, `=64` ingestion |
| 2 | Qdrant RAM spike | RSS > 4GB in metrics | `memmap_threshold=5000`, `on_disk=True` |
| 3 | Cross-encoder timeout | Langfuse span > 2000ms | Hard cap rerank input at 15 docs |
| 4 | KeyDB fork OOM | KeyDB crash during snapshot | Disable RDB, use AOF `appendfsync everysec` |
| 5 | LiteLLM fallback loop | Exponential latency | Max 2 fallbacks, Redis semantic cache |
| 6 | Crawl4AI DOM hang | Worker stuck indefinitely | `page_timeout=30000`, depth limit |
| 7 | Docling PDF OOM | Container memory cap hit | Queue concurrency=1, file size limit 50MB |
| 8 | CF Worker CPU limit | Cloudflare dashboard errors | Keep Worker logic to SHA-256 + KV only |
| 9 | PostgreSQL conn starvation | Pool timeout in FastAPI | PgBouncer + `pool_size = workers * 2` |
| 10 | DSPy MIPROv2 API blowout | LLM billing spike | `auto="light"`, KeyDB cache DSPy evals |
