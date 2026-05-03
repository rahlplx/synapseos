# SynapseOS — API Reference

> Base URL: `https://api.synapseos.com/v1`
> Auth: `Authorization: Bearer {api_key}` + `X-Tenant-ID: {tenant_id}`

---

## Endpoints

### POST /v1/query

Stream a RAG query over SSE.

**Request**
```json
{
  "question": "What was our Q3 campaign ROI?",
  "top_k": 5,
  "stream": true,
  "use_hyde": false
}
```

**Response** (SSE stream)
```
data: {"chunk": "Based on the Q3 report, "}
data: {"chunk": "your campaign achieved a 3.2x ROI..."}
data: {"done": true, "trace_id": "lf-abc123", "sources": [...]}
```

**Response** (non-stream)
```json
{
  "answer": "Based on the Q3 report...",
  "sources": [
    {"chunk_id": "...", "text": "...", "score": 0.92, "source_url": "..."}
  ],
  "trace_id": "lf-abc123",
  "latency_ms": 312
}
```

---

### POST /v1/ingest

Queue document ingestion. Returns job ID immediately.

**Request**
```json
{
  "urls": ["https://docs.example.com/policy", "https://example.com/faq"],
  "metadata": {"category": "policy", "language": "en"}
}
```

**Response**
```json
{
  "job_id": "job-abc123",
  "status": "queued",
  "document_count": 2
}
```

---

### GET /v1/ingest/{job_id}

Poll ingestion job status.

**Response**
```json
{
  "job_id": "job-abc123",
  "status": "done",           // queued | processing | done | failed
  "chunk_count": 47,
  "elapsed_ms": 8420
}
```

---

### POST /v1/ingest/file

Upload a file (PDF, DOCX, TXT, MD) for ingestion.

**Request**: `multipart/form-data`, field `file`.

**Response**: Same as POST /v1/ingest.

---

### POST /v1/feedback

Submit thumbs up / thumbs down for a completed query.

**Request**
```json
{
  "trace_id": "lf-abc123",
  "rating": 1         // +1 positive, -1 negative
}
```

---

### GET /v1/collections

List all document collections for the tenant.

**Response**
```json
{
  "tenant_id": "org-xyz",
  "vector_count": 12450,
  "document_count": 89,
  "chunk_count": 12450,
  "storage_bytes": 94371840
}
```

---

### DELETE /v1/documents/{document_id}

Remove a document and all its vectors from Qdrant.

**Response**
```json
{ "deleted": true, "chunks_removed": 23 }
```

---

### GET /v1/analytics

RAGAS score trends + usage metrics.

**Response**
```json
{
  "ragas_7d": {
    "faithfulness": 0.82,
    "answer_relevancy": 0.79,
    "context_precision": 0.74
  },
  "queries_7d": 1247,
  "cache_hit_rate": 0.43,
  "top_queries": ["...", "..."]
}
```

---

### GET /v1/datasets

List exported fine-tuning datasets in MinIO.

**Response**
```json
{
  "datasets": [
    {
      "version": "v1",
      "sft_path": "datasets/v1/sft_train.jsonl",
      "dpo_path": "datasets/v1/dpo_train.jsonl",
      "sft_count": 312,
      "dpo_count": 87,
      "exported_at": "2026-05-04T02:00:00Z"
    }
  ]
}
```

---

## Python SDK

### Installation

```bash
pip install synapseos
```

### Usage

```python
import asyncio
from synapseos import AsyncSynapseClient

client = AsyncSynapseClient(
    base_url="https://api.synapseos.com",
    api_key="sk-syn-...",
    tenant_id="org-xyz",
)

async def main():
    # Non-streaming query
    result = await client.query("What is our refund policy?")
    print(result.answer)
    print(result.sources)

    # Streaming query
    async for chunk in client.query_stream("Summarize Q3 performance"):
        print(chunk, end="", flush=True)

    # Ingest URLs
    job = await client.ingest(urls=["https://docs.mysite.com"])
    print(job.job_id)

    # Submit feedback
    await client.feedback(trace_id="lf-abc123", rating=1)

asyncio.run(main())
```

### Client Implementation

```python
# synapseos/client.py
import httpx
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class QueryResult:
    answer: str
    sources: list[dict]
    trace_id: str
    latency_ms: int

@dataclass
class IngestJob:
    job_id: str
    status: str

class AsyncSynapseClient:
    def __init__(self, base_url: str, api_key: str, tenant_id: str):
        self._base = base_url.rstrip("/") + "/v1"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Tenant-ID": tenant_id,
            "Content-Type": "application/json",
        }

    async def query(
        self,
        question: str,
        top_k: int = 5,
        use_hyde: bool = False,
    ) -> QueryResult:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{self._base}/query",
                headers=self._headers,
                json={"question": question, "top_k": top_k,
                      "stream": False, "use_hyde": use_hyde},
            )
            resp.raise_for_status()
            data = resp.json()
            return QueryResult(**data)

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120) as http:
            async with http.stream(
                "POST",
                f"{self._base}/query",
                headers=self._headers,
                json={"question": question, "top_k": top_k, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        import json
                        payload = json.loads(line[6:])
                        if "chunk" in payload:
                            yield payload["chunk"]
                        if payload.get("done"):
                            break

    async def ingest(self, urls: list[str], metadata: dict = None) -> IngestJob:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                f"{self._base}/ingest",
                headers=self._headers,
                json={"urls": urls, "metadata": metadata or {}},
            )
            resp.raise_for_status()
            data = resp.json()
            return IngestJob(job_id=data["job_id"], status=data["status"])

    async def feedback(self, trace_id: str, rating: int):
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(
                f"{self._base}/feedback",
                headers=self._headers,
                json={"trace_id": trace_id, "rating": rating},
            )
```

---

## TypeScript SDK

### Installation

```bash
npm install @synapseos/sdk
```

### Usage (SvelteKit)

```typescript
import { SynapseOSClient } from '@synapseos/sdk';

const client = new SynapseOSClient({
  baseUrl: import.meta.env.VITE_SYNAPSE_URL,
  apiKey: import.meta.env.VITE_SYNAPSE_KEY,
  tenantId: import.meta.env.VITE_TENANT_ID,
});

// Non-streaming
const result = await client.query("What is our refund policy?");
console.log(result.answer);

// Streaming
for await (const chunk of client.queryStream("Summarize Q3")) {
  process.stdout.write(chunk);
}

// Ingest
const job = await client.ingest({ urls: ["https://docs.example.com"] });
```

### SDK Implementation

```typescript
// src/index.ts
export interface QueryResult {
  answer: string;
  sources: Source[];
  traceId: string;
  latencyMs: number;
}

export interface Source {
  chunkId: string;
  text: string;
  score: number;
  sourceUrl?: string;
}

export class SynapseOSClient {
  private baseUrl: string;
  private headers: HeadersInit;

  constructor(config: { baseUrl: string; apiKey: string; tenantId: string }) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "") + "/v1";
    this.headers = {
      "Authorization": `Bearer ${config.apiKey}`,
      "X-Tenant-ID": config.tenantId,
      "Content-Type": "application/json",
    };
  }

  async query(question: string, topK = 5): Promise<QueryResult> {
    const resp = await fetch(`${this.baseUrl}/query`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ question, top_k: topK, stream: false }),
    });
    if (!resp.ok) throw new Error(`SynapseOS error: ${resp.status}`);
    const data = await resp.json();
    return {
      answer: data.answer,
      sources: data.sources,
      traceId: data.trace_id,
      latencyMs: data.latency_ms,
    };
  }

  async *queryStream(question: string, topK = 5): AsyncGenerator<string> {
    const resp = await fetch(`${this.baseUrl}/query`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ question, top_k: topK, stream: true }),
    });
    if (!resp.body) throw new Error("No response body");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const payload = JSON.parse(line.slice(6));
          if (payload.chunk) yield payload.chunk;
          if (payload.done) return;
        }
      }
    }
  }

  async ingest(params: { urls: string[]; metadata?: Record<string, string> }) {
    const resp = await fetch(`${this.baseUrl}/ingest`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(params),
    });
    return resp.json();
  }

  async feedback(traceId: string, rating: 1 | -1) {
    await fetch(`${this.baseUrl}/feedback`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ trace_id: traceId, rating }),
    });
  }
}
```

---

## MCP Server (FastMCP)

### Installation in Claude Code / Cursor / Windsurf

```bash
# Claude Code
fastmcp install claude synapse_mcp.py

# Cursor — add to .cursor/mcp.json
{
  "synapseos": {
    "command": "python",
    "args": ["synapse_mcp.py"],
    "env": {
      "SYNAPSE_API_KEY": "sk-syn-...",
      "SYNAPSE_BASE_URL": "https://api.synapseos.com"
    }
  }
}
```

### MCP Tool Definitions

```python
# synapse_mcp.py
from fastmcp import FastMCP
from synapseos import AsyncSynapseClient
import os

mcp = FastMCP("SynapseOS", instructions="Query organizational knowledge via RAG.")
client = AsyncSynapseClient(
    base_url=os.environ["SYNAPSE_BASE_URL"],
    api_key=os.environ["SYNAPSE_API_KEY"],
    tenant_id=os.environ.get("SYNAPSE_TENANT_ID", "default"),
)

@mcp.tool()
async def query_knowledge(question: str) -> str:
    """Query the knowledge base. Use for any factual question about organizational documents, policies, or content."""
    result = await client.query(question)
    sources = "\n".join(f"- {s['source_url']}" for s in result.sources if s.get("source_url"))
    return f"{result.answer}\n\nSources:\n{sources}"

@mcp.tool()
async def ingest_url(url: str) -> str:
    """Ingest a URL into the knowledge base. Use when asked to 'learn', 'read', or 'index' a document."""
    job = await client.ingest(urls=[url])
    return f"Ingestion queued. Job ID: {job.job_id}"

@mcp.tool()
async def submit_feedback(trace_id: str, positive: bool) -> str:
    """Submit feedback on a RAG response. positive=True for thumbs up, False for thumbs down."""
    await client.feedback(trace_id, 1 if positive else -1)
    return "Feedback recorded."

@mcp.tool()
async def get_collection_stats() -> str:
    """Get knowledge base statistics for the current tenant."""
    async with httpx.AsyncClient() as http:
        resp = await http.get(f"{client._base}/collections", headers=client._headers)
        data = resp.json()
    return f"Vectors: {data['vector_count']} | Documents: {data['document_count']}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## Error Codes

| Code | Meaning | Resolution |
|---|---|---|
| 401 | Missing X-Tenant-ID or API key | Add required headers |
| 403 | BYOK key not configured | Set provider API key in dashboard |
| 429 | Rate limit exceeded | Upgrade tier or reduce RPM |
| 503 | Backend unavailable | Cloudflare Workers edge cache may serve stale |
| 504 | Oracle ARM timeout | Cold start; retry after 3s |
