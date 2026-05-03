# SynapseOS — Build Sessions (chat.z.ai Web App)

> Rahul's daily vibe coding system using chat.z.ai FREE web app.
> One session = one focused feature. Small wins daily.

---

## Reality Check — chat.z.ai Free Web App

| What You Get | Reality |
|---|---|
| Model | GLM-5 now → GLM-5.1 rolling out to web soon |
| Daily usage | Free with a daily cap — hits limit on heavy sessions |
| Context window | 200K — paste entire files, works great |
| Memory between chats | ZERO — each new chat starts blank |
| Code execution | None — copy paste to repo manually |
| Web search | Yes — say "search the web for X" |
| File upload | Yes — drag .py .yaml .md directly into chat |
| Session continuity | Cannot resume yesterday's chat |

### When Daily Limit Hits — Backup Tools (all free)
- deepseek.com — DeepSeek V3, excellent for code
- claude.ai — best for architecture reasoning
- chat.mistral.ai — Codestral for pure code tasks

---

## MINI-CONTEXT (paste at start of EVERY new chat)

```
You are helping me build SynapseOS — a self-improving RAG platform.

LOCKED STACK:
- FastAPI + Uvicorn (Python 3.11)
- Qdrant 1.13.5 (dense + sparse BM25 hybrid vectors)
- fastembed BAAI/bge-base-en-v1.5 (768d, CPU only, ARM)
- LiteLLM → Groq primary → OpenRouter → Anthropic fallback
- mem0ai memory (Qdrant + PostgreSQL backend)
- Crawl4AI scraping | Docling PDF parsing | RAGAS evaluation | DSPy optimization
- KeyDB (Redis-compatible) | MinIO | Langfuse v3 | Cloudflare Workers
- Deploy: Coolify on Oracle ARM 4 vCPU / 24GB RAM, NO GPU

ARM RULES — never break:
- OMP_NUM_THREADS=4 always
- batch_size=64 ingestion, batch_size=16 query
- Cross-encoder input cap = 15 docs max
- KeyDB AOF only — NO RDB (fork causes OOM)
- Docling concurrency = 1
- Qdrant: on_disk=True, memmap_threshold_kb=50000

REPO: github.com/rahlplx/synapseos
I am non-technical. Give me complete production files I paste directly to repo.
Full files always. No snippets. No ellipsis shortcuts.
```

---

## Daily Ritual

```
1. Open chat.z.ai → New Chat
2. Paste MINI-CONTEXT → Enter → wait for confirmation
3. Paste today's session prompt → Enter
4. Copy each file output → paste into repo
5. Run the test command
6. Paste session log into AGENTS.md
7. Push to GitHub: git add -A && git commit -m "day N: feature" && git push
```

---

## Golden Rules for chat.z.ai

```
One chat = one feature
One message = one file request
If output cuts off → type "continue"
If it forgets → paste MINI-CONTEXT again
Always end file requests with: "Full file. No truncation. No ellipsis."
Drag files into chat instead of copy-pasting for big files
```

---

## PHASE 1 — Core RAG (Days 1–4)

### Day 1 — Docker: All Services Live

```
Today's task: get all Docker services healthy on Oracle ARM.

[Drag docker-compose.yml into chat]
[Drag .env.example into chat]

1. Check docker-compose.yml for ARM issues
2. List every .env value I need to fill, one by one with instructions
3. Exact terminal commands to:
   a. Install Docker + Compose on Oracle ARM Ubuntu if needed
   b. Clone repo from github.com/rahlplx/synapseos
   c. cp .env.example .env and fill values
   d. docker compose up -d
   e. Check each service is healthy
4. What scripts/healthcheck.sh output looks like when all pass

Give me a numbered checklist I follow step by step.
No assumptions about what I know.
```

---

### Day 2 — Qdrant Collection + First Ingest

```
Today's task: create Qdrant collection and ingest a real URL.

[Drag src/core/ingestion.py into chat]
[Drag src/core/retrieval.py into chat]

1. Check both files for ARM issues (batch sizes, threads, Docling)
2. Write complete scripts/setup_collection.py:
   - Creates synapse_knowledge collection (dual vectors: dense + sparse)
   - Creates tenant_id payload index
   - Prints confirmation and collection info
3. Write complete scripts/test_ingest.py:
   - Ingests: https://qdrant.tech/documentation/concepts/
   - tenant_id = "test"
   - Prints: chunks stored, time taken, memory used
4. Commands to run both
5. How to verify vectors in Qdrant dashboard at port 6333

Full files. Complete scripts.
```

---

### Day 3 — Hybrid Query Working

```
Today's task: hybrid RAG query returning ranked chunks.

[Drag src/core/retrieval.py into chat]
Qdrant has vectors from Day 2.

1. Check hybrid_query() for correctness:
   - Dense embed + BM25 sparse both running
   - Qdrant Query API with prefetch + RRF
   - Cross-encoder rerank capped at 15 docs
   - tenant_id filter on every query
2. Fix issues. Complete corrected retrieval.py
3. Write complete scripts/test_retrieval.py:
   - Runs hybrid_query("how does HNSW indexing work?", tenant_id="test")
   - Prints top 5 chunks with scores
   - Prints latency per phase (embed / qdrant / rerank)
   - Compares hybrid vs dense-only score difference
4. Run command

Full corrected retrieval.py + complete test script.
```

---

### Day 4 — /v1/query Endpoint Live

```
Today's task: streaming API endpoint returning Groq answers.

[Drag src/api/main.py into chat]
[Drag src/api/routes/query.py into chat]
[Drag src/api/middleware/tenant.py into chat]
[Drag src/core/generation.py into chat]

1. Check all 4 files together for issues:
   - Groq API via GROQ_API_KEY env var
   - SSE streaming: data: {"chunk": "..."}\n\n format
   - TenantMiddleware injects tenant_id before route fires
   - LiteLLM fallback chain working
2. Fix issues. Complete corrected files (show each separately)
3. Start command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
4. curl test:
   curl -X POST http://localhost:8000/v1/query
     -H "X-Tenant-ID: test"
     -H "Content-Type: application/json"
     -d '{"question":"what is HNSW?","stream":true}'
5. Expected streaming output format

Phase 1 complete when curl returns streaming chunks.
```

---

## PHASE 2 — SDK + Edge (Days 5–8)

### Day 5 — Python SDK Working

```
Today's task: Python SDK tested against live API.

[Drag sdk/python/synapseos/client.py into chat]
API is live at http://YOUR_IP:8000

1. Fix any issues in AsyncSynapseClient
2. Write complete scripts/test_sdk_python.py:
   - query() non-streaming — print answer
   - query_stream() — print chunks as they arrive
   - ingest(["https://docs.python.org"]) — poll until done
   - feedback(trace_id, +1)
   - PASS/FAIL for each test
3. Install command: pip install -e sdk/python/
4. Run command: python scripts/test_sdk_python.py
5. Complete fixed client.py
```

---

### Day 6 — TypeScript SDK + SvelteKit Widget

```
Today's task: TypeScript SDK + streaming chat widget.

[Drag sdk/typescript/src/index.ts into chat]

1. Fix SynapseOSClient TypeScript issues
2. Write complete src/lib/components/RAGChatWidget.svelte:
   - queryStream() tokens appear in real time
   - Input + Send button (Enter key works)
   - Thinking... spinner while streaming
   - Sources list after answer
   - Thumbs up/down feedback buttons
   - shadcn-svelte styling
3. Write complete src/routes/api/chat/+server.ts (SSE proxy, avoids CORS)
4. How to add to existing SvelteKit app in 3 steps
5. Fixed index.ts

Give me: index.ts + ChatWidget.svelte + +server.ts
```

---

### Day 7 — MCP Server (Claude Code / Cursor / Windsurf)

```
Today's task: MCP server so AI coding tools can query SynapseOS.

[Drag mcp/synapse_mcp.py into chat]

1. Fix FastMCP 2.2.9 issues in synapse_mcp.py
2. Add tool: check_job_status(job_id: str)
3. Installation: pip install fastmcp
4. Run: python mcp/synapse_mcp.py
5. Config files (show each as complete JSON):
   a. ~/.cursor/mcp.json
   b. Claude Code: ~/Library/Application Support/Claude/claude_desktop_config.json
   c. Windsurf settings
6. Test: what Claude Code shows when I type "@SynapseOS query_knowledge what is BM25?"

Give me: fixed synapse_mcp.py + all 3 config files.
```

---

### Day 8 — Cloudflare Workers Edge Cache

```
Today's task: Cloudflare Workers caching SynapseOS at the edge.

[Drag cloudflare/worker.ts into chat]
Oracle ARM API at: https://api.synapseos.com

1. Fix worker.ts:
   - SHA-256 hash includes X-Tenant-ID (prevents cross-tenant cache)
   - stream:true requests bypass cache entirely
   - Non-streaming cached in KV with TTL
2. Complete wrangler.toml
3. Deployment steps:
   npm install -g wrangler
   wrangler login
   wrangler kv:namespace create RAG_CACHE
   wrangler deploy
4. Set ORACLE_BACKEND secret in Cloudflare dashboard
5. Verify: first request X-Cache: MISS, second X-Cache: HIT <50ms

Give me: fixed worker.ts + complete wrangler.toml + all commands.
```

---

## PHASE 3 — Cognitive Engine (Days 9–12)

### Day 9 — Memory (mem0)

```
Today's task: SynapseOS remembers facts between conversations.

[Drag src/cognitive/memory.py into chat]

1. Fix memory.py:
   - mem0 Qdrant config → synapse_memory collection
   - Groq Llama-8b as LLM judge (it's already in the file)
   - fastembed as embedder
   - KeyDB session cache 10-turn sliding window
2. Complete corrected memory.py
3. Write complete scripts/test_memory.py:
   Turn 1 (user_id=rahul): "My name is Rahul, I run an agency in Bangladesh"
   Turn 2 (NEW CHAT, same user_id): "What do I do for work?"
   Turn 2 must answer from memory without Turn 1 in context
   Print: facts extracted, facts recalled, answer
4. How to verify synapse_memory collection in Qdrant dashboard
5. Run command. If ARM install issues with mem0, show fix.
```

---

### Day 10 — Self-Reflection

```
Today's task: GLM answers evaluated and improved before returning.

[Drag src/cognitive/reflection.py into chat]

1. Fix reflect_and_refine():
   - Groq Llama-8b as judge
   - JSON parsing with fallback if malformed
   - threshold=0.70, max 1 retry, hard stop
2. Complete corrected reflection.py
3. Write complete scripts/test_reflection.py:
   Case A: Good answer (score ≥ 0.7) → returned as-is
   Case B: Vague answer (score < 0.7) → retried once → better
   Case C: Hallucinated claim → caught → corrected
   Print scores + retry flag for each
4. Update src/api/routes/query.py to call reflect_and_refine() after generate()
   Show complete updated query.py

Give me: fixed reflection.py + updated query.py + test script.
```

---

### Day 11 — Tool Executor

```
Today's task: SynapseOS can use tools (web search, calculate, APIs).

[Drag src/cognitive/tools.py into chat]
[Drag src/core/generation.py into chat]

1. Fix ToolExecutor 4 built-in tools:
   - retrieve_knowledge: calls hybrid_query
   - web_search: Crawl4AI → Brave search (15s timeout)
   - calculate: safe eval, numbers+operators only
   - call_api: DB lookup, Fernet decrypt, httpx call
2. Add generate_with_tools() to generation.py:
   - LiteLLM function calling (Groq supports it)
   - Parallel tool execution with asyncio.gather
   - Append results and get final answer
3. Write complete scripts/test_tools.py:
   - web_search("Qdrant 1.13 release notes") → real web content
   - calculate("(42 * 1.5) + 10") → 73.0
   - retrieve_knowledge("what is BM25") → chunks from Qdrant

Give me: fixed tools.py + updated generation.py + test script.
```

---

### Day 12 — /v1/think — Full Cognitive Engine

```
Today: final boss. Wire everything into /v1/think.

[Drag src/cognitive/engine.py into chat]
[Drag src/api/routes/think.py into chat]

1. Fix cognitive_query() orchestrator all 5 steps:
   - Step 1: memory load (parallel KeyDB + mem0)
   - Step 2: classify (simple/complex/tool)
   - Step 3: execute correct path
   - Step 4: reflect_and_refine()
   - Step 5: write_memory as asyncio.create_task (non-blocking)
2. Complete fixed engine.py and think.py
3. Write complete scripts/test_think.py:
   Test A (simple): "what is HNSW indexing?" → knowledge base
   Test B (memory): "what is my name?" → uses mem0 (set Day 9)
   Test C (tool): "search web for Qdrant 2025 updates" → web_search
   Print: query_type, tools_used, memories_recalled, reflection_scores
4. Final curl:
   curl -X POST http://localhost:8000/v1/think
     -H "X-Tenant-ID: test"
     -H "Content-Type: application/json"
     -d '{"question":"What is my name?","session_id":"s001","user_id":"rahul"}'

SynapseOS done when all 3 test types pass.
```

---

## Session Log Format (paste into AGENTS.md after each day)

```markdown
## Session YYYY-MM-DD — Day N: [feature built]
- Built: [description]
- Files changed: [list]
- Test: [command]
- Status: done / partial / blocked
- Next: Day N+1 — [what to build]
```
