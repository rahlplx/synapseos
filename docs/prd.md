# SynapseOS — Product Requirements Document

> Version: 1.0.0 | Owner: Rahul Paul / Lab Launchpad | May 2026

---

## Product Vision

SynapseOS is a standalone BYOK RAG platform with SDK and MCP server. It lets any application — AgencyOS, ForkOS, or third-party software — embed intelligent, self-improving knowledge retrieval without building retrieval infrastructure. Tenants bring their own LLM keys, upload their own knowledge, and get a streaming RAG API that gets smarter every night.

**Target markets**: Bangladesh-first (AgencyOS module), UK F&B (ForkOS embed), developer ecosystem (SDK + MCP).

---

## User Personas

| Persona | Pain Point | SynapseOS Job |
|---|---|---|
| Agency Founder (BD) | No affordable RAG for client knowledge bases | M-RAG module in AgencyOS, BDT pricing |
| Developer (Global) | Build RAG from scratch takes weeks | SDK installed in <5 min, MCP in <2 min |
| Restaurant Operator (UK) | Manual FAQ answering | ForkOS embed with menu/policy knowledge |
| Vibe Coder | No-code ingestion, chat widget | Dashboard + drag-drop ingest UI |

---

## Feature Matrix

### Core Platform

| Feature | v1.0 | v1.5 | v2.0 |
|---|---|---|---|
| Hybrid retrieval (dense + BM25 + rerank) | ✅ | ✅ | ✅ |
| Multi-tenant isolation (payload filter) | ✅ | ✅ | ✅ |
| BYOK (Groq / OpenRouter / Anthropic) | ✅ | ✅ | ✅ |
| SSE streaming responses | ✅ | ✅ | ✅ |
| Web scraping (Crawl4AI) | ✅ | ✅ | ✅ |
| PDF/DOCX parsing (Docling) | ✅ | ✅ | ✅ |
| RAGAS auto-evaluation | ✅ | ✅ | ✅ |
| SFT/DPO dataset export | ✅ | ✅ | ✅ |
| DSPy MIPROv2 nightly optimization | ✅ | ✅ | ✅ |
| Langfuse self-hosted observability | ✅ | ✅ | ✅ |
| Python SDK | ✅ | ✅ | ✅ |
| TypeScript SDK | ✅ | ✅ | ✅ |
| FastMCP MCP server | ✅ | ✅ | ✅ |
| Cloudflare Workers edge cache | ✅ | ✅ | ✅ |
| AgencyOS M-RAG module | ✅ | ✅ | ✅ |
| HyDE query expansion | — | ✅ | ✅ |
| Dedicated tenant collections (high-traffic) | — | ✅ | ✅ |
| Bengali language embeddings | — | ✅ | ✅ |
| bKash/Nagad billing | — | ✅ | ✅ |
| ForkOS embed | — | — | ✅ |
| Droid AI (Android BYOK) | — | — | ✅ |

---

## AgencyOS M-RAG Module Spec

SynapseOS embeds into AgencyOS as module M-RAG. It shares the AgencyOS PostgreSQL database (with `synapseos_` table prefix) and Qdrant instance (shared collection, `tenant_id = org_id`).

### Module Routes (FastAPI)

```
POST   /modules/rag/ingest          — queue document ingestion
GET    /modules/rag/documents       — list tenant documents
DELETE /modules/rag/documents/{id}  — remove document + vectors
POST   /modules/rag/query           — streaming RAG query
POST   /modules/rag/feedback        — thumbs up/down
GET    /modules/rag/analytics       — RAGAS score trends, usage
GET    /modules/rag/datasets        — list MinIO JSONL exports
```

### SvelteKit Chat Widget

```svelte
<!-- src/lib/components/RAGChatWidget.svelte -->
<script lang="ts">
  import { writable } from 'svelte/store';
  import { SynapseOSClient } from '@synapseos/sdk-ts';

  export let apiKey: string;
  export let tenantId: string;

  const client = new SynapseOSClient(
    import.meta.env.VITE_SYNAPSE_URL,
    apiKey,
    tenantId
  );

  let messages = writable<{ role: string; content: string }[]>([]);
  let inputValue = '';
  let loading = false;

  async function sendMessage() {
    if (!inputValue.trim()) return;
    const question = inputValue;
    inputValue = '';
    loading = true;

    messages.update(m => [...m, { role: 'user', content: question }]);

    const stream = await client.queryStream(question);
    let assistant = '';
    messages.update(m => [...m, { role: 'assistant', content: '' }]);

    for await (const chunk of stream) {
      assistant += chunk;
      messages.update(m => {
        const updated = [...m];
        updated[updated.length - 1].content = assistant;
        return updated;
      });
    }
    loading = false;
  }
</script>
```

**Pattern**: SvelteKit `+server.ts` endpoint proxies SSE to avoid CORS. Never expose SynapseOS API key client-side.

---

## Pricing Tiers (Bangladesh BDT + UK GBP)

### Bangladesh / AgencyOS Market

| Tier | BDT/month | Queries | Documents | Tenants |
|---|---|---|---|---|
| Starter | ৳999 | 1,000 | 50 | 1 |
| Growth | ৳2,499 | 5,000 | 500 | 5 |
| Pro | ৳5,999 | 25,000 | Unlimited | 25 |

### UK / Global Developer Market

| Tier | £/month | Queries | Documents | Notes |
|---|---|---|---|---|
| Developer | Free | 100 | 10 | SDK access |
| Starter | £19 | 2,000 | 100 | 1 tenant |
| Growth | £49 | 10,000 | 1,000 | 10 tenants |
| Pro | £149 | 50,000 | Unlimited | 100 tenants + SLA |

**Billing hooks**: Usage metered per query + per 1K tokens via PostgreSQL `usage_records`. bKash/Nagad: `transactbd==1.0.0`. Stripe for UK market.

---

## Non-Functional Requirements

| Requirement | Target |
|---|---|
| P95 query latency (warm, no HyDE) | < 400ms |
| P95 ingestion latency (per chunk) | < 2s |
| Uptime | 99.5% (Oracle ARM SLA) |
| Max RAM at peak | 24GB (hard cap) |
| Edge cache hit rate | > 40% (semantic threshold 0.92) |
| RAGAS faithfulness baseline | > 0.7 |
| Cold start (Cloudflare Workers) | < 5ms |
| Docling concurrency | 1 (sequential queue) |
| Dataset export frequency | Nightly 02:00 UTC |
| Fine-tune cycle (Qwen3-4B) | Weekly if > 100 new pairs |

---

## Security Requirements

- BYOK keys encrypted at rest: Fernet AES-256 in PostgreSQL
- Keys never logged, never in environment files
- Tenant data isolated: `tenant_id` payload filter on all Qdrant queries
- API authentication: Bearer token per tenant
- Rate limiting: KeyDB sliding window before any ONNX execution
- HTTPS everywhere: Cloudflare termination + Coolify Traefik
- MinIO bucket policies: tenant-scoped path `/{tenant_id}/`
