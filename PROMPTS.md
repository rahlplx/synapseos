# SynapseOS — Agent Mode Prompts

> Written specifically for chat.z.ai Agent Mode (GLM-5 / GLM-5.1).
> Agent Mode ≠ Chat Mode. Agent thinks in steps, uses tools, self-corrects.
> Each prompt is a complete TASK — not a question. Give the agent the task and let it run.

---

## How Agent Mode Works (read once)

In chat.z.ai, switch to **Agent** mode before starting (toggle in the interface).
In Agent mode, GLM-5 will:
- Search the web for current docs automatically when needed
- Think step by step before writing code
- Self-check its own output for errors
- Chain multiple operations in one response
- Deliver complete, runnable files

**Because of this, each prompt here covers more ground than chat-mode prompts.**
One agent task = what would take 3-4 chat prompts.

**How to use this file:**
1. Open chat.z.ai → switch to Agent mode
2. Copy the SYSTEM CONTEXT block (once per day, first message)
3. Copy the SESSION TASK for today → paste → let agent run
4. When agent finishes, copy each file output → paste into repo
5. Run the validation command the agent gives you
6. If validation fails, paste the error back — agent self-corrects

---

## SYSTEM CONTEXT — Paste Once at Start of Every Session

```
You are an expert Python/TypeScript engineer helping build SynapseOS.

PROJECT: SynapseOS — self-improving BYOK RAG platform with cognitive engine
REPO: github.com/rahlplx/synapseos (scaffold already exists)
DEPLOY: Oracle ARM A1 — 4 vCPU / 24GB RAM — NO GPU — Coolify

LOCKED STACK (search docs for any package you're unsure about, never guess versions):
- FastAPI 0.115 + Uvicorn | Python 3.11 | asyncpg
- Qdrant 1.13.5 — hybrid: dense (768d) + sparse BM25 + RRF + cross-encoder rerank
- fastembed BAAI/bge-base-en-v1.5 — ONNX, CPU-only, 768 dimensions
- LiteLLM 1.82.9 — Groq primary → OpenRouter → Anthropic fallback, BYOK per tenant
- mem0ai — Qdrant synapse_memory collection + PostgreSQL backend
- Crawl4AI 0.4.3 — async web scraping, JS-rendered pages
- Docling 2.19.0 — PDF/DOCX layout-aware parsing → clean markdown
- RAGAS 0.2.15 — reference-free RAG evaluation
- DSPy 2.5.20 — MIPROv2 prompt optimization
- Langfuse v3 — self-hosted observability
- KeyDB 6.3.4 — Redis-compatible cache + job queue
- MinIO — S3-compatible object storage
- FastMCP 2.2.9 — MCP server for Claude Code / Cursor / Windsurf
- Cloudflare Workers — edge proxy + KV cache

CRITICAL ARM CPU CONSTRAINTS (never violate):
  os.environ["OMP_NUM_THREADS"] = "4"  # set before fastembed import
  BATCH_INGEST = 64    # embedding batch for ingestion
  BATCH_QUERY  = 16    # embedding batch for real-time query
  RERANK_MAX   = 15    # hard cap on cross-encoder input docs
  DOCLING_CPU_ONLY = "1"           # env var required
  Docling concurrency = 1          # never parallel
  KeyDB: appendonly yes + save ""  # AOF only, NO RDB fork
  Qdrant: on_disk=True, memmap_threshold_kb=50000

COLLECTIONS: synapse_knowledge (RAG docs) | synapse_memory (mem0 user memory)
LLM: groq/llama-3.1-70b-versatile (generation) | groq/llama-3.1-8b-instant (fast tasks)

CODE STANDARDS:
- All functions async/await
- All secrets via os.environ — never hardcoded
- Complete files only — no partial code, no "# ... rest here ..."
- All imports at file top
- Type hints on all functions
- tenant_id payload filter on EVERY Qdrant query (never cross-tenant)
- Fernet AES-256 for encrypting BYOK keys in PostgreSQL
- Memory writes always asyncio.create_task() — never block response

Acknowledge with: "SynapseOS context loaded. Ready for today's task."
```

---

## PRE-BUILD — Fix Existing Partial Code (Day 0)

> Run this ONCE before starting Day 1 if you haven't yet.
> The scaffold exists but has gaps. This session closes them all.

### SESSION TASK — Day 0: Close All Gaps

```
OBJECTIVE: Complete all partial implementations in the existing SynapseOS scaffold.

CONTEXT: The repo at github.com/rahlplx/synapseos has scaffold code with these known gaps:
1. src/api/routes/ingest.py — missing GET /v1/ingest/{job_id} endpoint (job status polling)
2. src/api/routes/collections.py — missing DELETE /v1/documents/{id} and analytics endpoint
3. src/api/routes/query.py — reflection not wired in after generation
4. src/core/generation.py — missing generate_with_tools() for LiteLLM function calling
5. src/cognitive/tools.py — call_api tool is a TODO stub
6. src/cognitive/engine.py — complex path uses TODO instead of DSPy ReAct
7. src/worker/nightly_optimizer.py — entire implementation is a placeholder

TASK: Implement all 7 gaps. For each file, search the web for current package APIs if needed.

FILE 1 — src/api/routes/ingest.py
Add GET /v1/ingest/{job_id} that:
- Reads job status from KeyDB hash "job:{job_id}"
- Returns: {job_id, status, chunk_count (if done), elapsed_ms, error (if failed)}
Show complete updated file.

FILE 2 — src/api/routes/collections.py
Add:
- DELETE /v1/documents/{document_id} — deletes document from PG + filters Qdrant points by doc_id
- GET /v1/analytics — returns RAGAS score 7-day trend from interaction_logs table
Show complete updated file.

FILE 3 — src/api/routes/query.py
Wire reflect_and_refine() after generation:
- For non-streaming: generate → reflect → return {answer, sources, reflection_scores, retried}
- For streaming: stream tokens, collect full answer, reflect, stream reflected answer
- If reflection throws: return original answer, never fail the request
Show complete updated file.

FILE 4 — src/core/generation.py
Add async generate_with_tools(question, context, available_tools, tenant_api_key) that:
- Calls LiteLLM with tools= parameter (OpenAI function calling format)
- Uses groq/llama-3.1-70b-versatile (Groq supports function calling)
- If tool_calls in response: runs all via asyncio.gather using ToolExecutor
- Appends tool results to messages, calls LiteLLM again for final answer
- Returns tuple: (final_answer_text, list_of_tool_names_used)
Show complete updated file.

FILE 5 — src/cognitive/tools.py
Implement call_api tool:
- Load tool from PostgreSQL: SELECT * FROM tools WHERE tenant_id=$1 AND name=$2 AND active=TRUE
- Decrypt auth_header with Fernet cipher
- Execute HTTP call via httpx.AsyncClient timeout=15
- Return response.text[:3000]
Show complete updated file.

FILE 6 — src/cognitive/engine.py
Replace complex path TODO with working implementation:
- Load session + memories (already parallel with asyncio.gather)
- Build enriched context: session_str + long_term_memory + retrieved chunks
- Call generate() with full context (DSPy ReAct deferred to Phase 3 — use enriched RAG for now)
- Set steps=2 to indicate multi-source synthesis
Show complete updated file.

FILE 7 — src/worker/nightly_optimizer.py
Implement score_and_export() that:
1. Fetches unscored interaction_logs from PostgreSQL (ragas_combined IS NULL, limit 100)
2. For each log, runs RAGAS evaluate() with faithfulness + answer_relevancy + context_precision
3. Updates ragas_faithfulness, ragas_relevancy, ragas_precision, ragas_combined in DB
4. Exports SFT JSONL (combined >= 0.7): ChatML format {messages: [{role, content}]}
5. Exports DPO JSONL (chosen=highest score, rejected=lowest for same query)
6. Uploads both to MinIO at datasets/v{date}/sft_train.jsonl and dpo_train.jsonl
7. Marks exported logs as dataset_exported=TRUE
Show complete updated file.

ACCEPTANCE CRITERIA:
- All 7 files are complete with no TODO comments remaining
- No placeholder strings or "implement later" comments
- All imports present
- All ARM constraints respected

OUTPUT CONTRACT:
Show each file as a complete, separate code block in this order:
1. ingest.py  2. collections.py  3. query.py  4. generation.py
5. tools.py   6. engine.py       7. nightly_optimizer.py
```

---

## PHASE 1 — Infrastructure

---

### SESSION TASK — Day 1A: Server Setup

```
OBJECTIVE: Prepare Oracle ARM Ubuntu 22.04 server with all prerequisites.

CONTEXT: Fresh Oracle ARM server. Need Docker, Docker Compose, Git installed.
I am non-technical and running commands via SSH.

TASK:
1. Write the exact sequence of shell commands to:
   a. Update system packages
   b. Install Docker Engine (official Docker, not snap version)
   c. Install Docker Compose plugin (not standalone docker-compose)
   d. Install Git
   e. Add ubuntu user to docker group (no sudo needed after)
   f. Verify all three work: docker --version, docker compose version, git --version

2. Write a verification one-liner I run to confirm everything is ready:
   Should print "READY" if all three are installed, "MISSING: X" if not

3. List the 3 most common errors on Oracle ARM during Docker install and their exact fixes

FORMAT: Numbered shell commands I copy-paste exactly. No explanations between commands.

ACCEPTANCE CRITERIA:
- docker compose ps runs without error
- git clone works
- No sudo needed for docker commands after logout/login
```

### SESSION TASK — Day 1B: Clone, Configure, Launch

```
OBJECTIVE: Clone repo, configure environment, start all Docker services, verify healthy.

CONTEXT: Server has Docker + Git. Running as ubuntu user.

TASK:
1. Clone repo:
   git clone https://github.com/rahlplx/synapseos /home/ubuntu/synapseos
   cd /home/ubuntu/synapseos

2. Generate all required secret values for .env:
   Write a Python one-liner for ENCRYPTION_KEY (Fernet)
   Write a shell command for random 32-char strings (NEXTAUTH_SECRET, SALT)
   Show exactly which values to fill from external services:
   - GROQ_API_KEY → console.groq.com → API Keys
   - OPENROUTER_API_KEY → openrouter.ai → Keys
   - ANTHROPIC_API_KEY → console.anthropic.com → API Keys

3. Show the complete .env file with all values filled in
   (use realistic placeholder values for secrets, show format)

4. Run services and verify:
   docker compose up -d
   docker compose ps (what healthy output looks like)
   
5. Initialize database and storage:
   Command to run init-db.sql against postgres container
   Command to run init-minio.sh
   
6. Run healthcheck and show expected output:
   ./scripts/healthcheck.sh

ACCEPTANCE CRITERIA:
- docker compose ps shows all 7 containers as "Up" or "healthy"
- PostgreSQL tables exist (verify with docker exec)
- MinIO bucket "synapseos" exists
- Langfuse UI accessible at :3100
- Qdrant dashboard accessible at :6333/dashboard

OUTPUT: Complete sequence of commands with expected output shown after each.
```

---

## PHASE 2 — Core RAG Engine

---

### SESSION TASK — Day 2A: Qdrant + First Ingest

```
OBJECTIVE: Create Qdrant collections and successfully ingest a real URL. Verify vectors stored.

CONTEXT: All Docker services running from Day 1. Writing scripts/ test files.

TASK:
Write scripts/setup_collection.py — complete standalone script that:
1. Connects to Qdrant at http://localhost:6333
2. Creates "synapse_knowledge" collection:
   - Dense vector: size=768, distance=Cosine, on_disk=True
   - Sparse vector: Qdrant/bm25 with IDF modifier  
   - optimizers: memmap_threshold_kb=50000, max_segment_size_kb=65536
3. Creates payload index on tenant_id (keyword type)
4. Creates "synapse_memory" collection with same vector config (for mem0)
5. Creates payload index on user_id for synapse_memory
6. Prints summary: collection name, vector count, status

Write scripts/test_ingest.py — complete standalone script that:
1. Calls setup_collection() first
2. Imports ingest_urls from src.core.ingestion
3. Ingests: https://qdrant.tech/documentation/concepts/collections/
   tenant_id="test", metadata={"category": "docs"}
4. Prints live progress at each pipeline stage with timing
5. Final report:
   ✅ Scraped: X chars of markdown
   ✅ Chunked: X chunks (after dedup)
   ✅ Embedded: Xms per chunk average
   ✅ Stored: X vectors in Qdrant
   Total time: X.Xs | RAM delta: +XMB
6. Queries Qdrant to verify: prints vector count for tenant "test"

ARM NOTE: Set OMP_NUM_THREADS=4 before importing fastembed. Use psutil for RAM.

ACCEPTANCE CRITERIA:
- setup_collection.py completes without error
- test_ingest.py stores >= 10 vectors
- Qdrant dashboard at :6333/dashboard shows synapse_knowledge collection with vectors
- No OOMKilled errors in docker logs qdrant

OUTPUT: Two complete Python scripts. Include: pip install psutil if needed.
```

### SESSION TASK — Day 2B: Hybrid Query Benchmarked

```
OBJECTIVE: Hybrid RAG query returning relevant chunks under 400ms. Benchmark proves hybrid > dense.

CONTEXT: Vectors in Qdrant from Day 2A. Testing src/core/retrieval.py.

TASK:
First, search the web for "qdrant query_points prefetch RRF fusion python 2025" to verify the current API.
Then review src/core/retrieval.py (I will paste it below) for ARM correctness.

[paste contents of src/core/retrieval.py]

Fix any issues then write scripts/test_retrieval.py — complete script that:

Test 1 — Hybrid query correctness:
  hybrid_query("how does HNSW graph indexing work?", tenant_id="test")
  Print top 5 results: [rank] score | first 120 chars of text

Test 2 — Phase timing breakdown:
  Use time.perf_counter() around each phase:
  Phase A: dense + sparse embed
  Phase B: Qdrant prefetch + RRF
  Phase C: cross-encoder rerank
  Print: Phase A: Xms | Phase B: Xms | Phase C: Xms | Total: Xms
  Status: ✅ FAST (< 400ms) or ⚠️ SLOW (> 400ms)

Test 3 — Hybrid vs dense-only comparison:
  Run same query dense-only (no sparse prefetch, no reranker)
  Print top 3 from hybrid vs top 3 from dense-only
  Count chunks that are different between the two
  Print: "Hybrid found X/3 unique chunks not in dense-only results"

Test 4 — Keyword precision test:
  Query: "memmap_threshold_kb configuration" (specific keyword)
  Hybrid should rank exact-match chunks higher than dense
  Print which position the exact-match chunk appears in hybrid vs dense-only

ACCEPTANCE CRITERIA:
- Total latency < 400ms on Oracle ARM
- Hybrid finds at least 1 different chunk than dense-only
- No cross-encoder input exceeds 15 docs
- tenant_id filter present in both prefetch queries

OUTPUT: Complete corrected retrieval.py + complete test script.
```

### SESSION TASK — Day 3: /v1/query Endpoint Live

```
OBJECTIVE: POST /v1/query returns streaming Groq answer with reflection scores. End-to-end working.

CONTEXT: Hybrid query works from Day 2. Testing full API stack.

TASK:
Search the web for "LiteLLM acompletion streaming SSE FastAPI 2025" for current patterns.

Review and fix these files (paste each below):
[paste src/api/main.py]
[paste src/api/middleware/tenant.py]
[paste src/api/routes/query.py]
[paste src/core/generation.py]

Issues to check:
- TenantMiddleware registered before routes in main.py
- Middleware skips /health, /docs, /openapi.json
- GROQ_API_KEY from os.environ in generation.py
- SSE format: exactly "data: {JSON}\n\n" per chunk, "data: {"done":true}\n\n" at end
- Reflection wired after generate() (from Day 0 fix)
- LiteLLM fallback: Groq → OpenRouter → Anthropic

Then write scripts/test_endpoint.py — complete script:

Test 1 — Non-streaming JSON response:
  POST /v1/query {question: "what is HNSW indexing?", stream: false}
  Print: status code, answer (first 300 chars), reflection_scores, retried, latency_ms
  PASS if status=200, answer non-empty, reflection_scores present

Test 2 — Streaming SSE:
  POST /v1/query {question: "explain BM25 sparse retrieval", stream: true}
  Print each chunk on same line as it arrives
  Print: chunk count, total streamed length, total time
  PASS if receives >= 5 chunks, done:true received

Test 3 — Rate limiting:
  Send 65 requests quickly for same tenant
  PASS if request 61+ returns HTTP 429

Test 4 — Missing tenant header:
  POST without X-Tenant-ID header
  PASS if returns HTTP 401

ACCEPTANCE CRITERIA:
- Test 1-4 all PASS
- Streaming latency: first chunk arrives < 2 seconds
- Non-streaming P95 < 1 second
- reflection_scores has: faithfulness, relevancy, completeness, combined fields

OUTPUT: All corrected files + complete test script + start command + curl demo command.
```

---

## PHASE 3 — SDK + Edge

---

### SESSION TASK — Day 4: Python SDK + TypeScript SDK

```
OBJECTIVE: Both SDKs fully working against live API. Install and test in < 10 minutes.

CONTEXT: /v1/query and /v1/think endpoints live from Day 3. SDK code in sdk/ directory.

TASK:
Review both SDK files (paste below):
[paste sdk/python/synapseos/client.py]
[paste sdk/typescript/src/index.ts]

For Python SDK, fix:
- query() handles non-streaming response parsing
- query_stream() correctly buffers SSE (partial lines across network packets)
- think() sends session_id and user_id, parses full cognitive response
- All timeouts set: query=60s, stream=120s, ingest=30s
- HTTP errors raise exceptions with status code in message

For TypeScript SDK, fix:
- queryStream() buffers correctly across ReadableStream chunks
- Stops on done:true not just on stream close
- Types: QueryResult, ThinkResult, IngestJob, Source interfaces complete

Write scripts/test_sdk.py:
1. pip install -e sdk/python/ first
2. Test query() → PASS/FAIL + answer snippet
3. Test query_stream() → PASS/FAIL + chunk count
4. Test think() → PASS/FAIL + query_type + memories_recalled
5. Test ingest() → PASS/FAIL + job_id
6. Test feedback() → PASS/FAIL
Summary: X/5 passed

Write sdk/typescript/tests/test_sdk.ts:
Equivalent 5 tests using Node.js fetch
Run with: npx ts-node test_sdk.ts

ACCEPTANCE CRITERIA:
- 5/5 Python tests pass
- 5/5 TypeScript tests pass
- SDK installable: pip install -e sdk/python/ with no errors

OUTPUT: Fixed client.py + fixed index.ts + test_sdk.py + test_sdk.ts
```

### SESSION TASK — Day 5: MCP Server + Cloudflare Workers

```
OBJECTIVE: MCP server working in Cursor/Claude Code. Cloudflare edge caching verified.

CONTEXT: API live. SDK tested. Now integrating with AI coding tools and edge.

TASK PART A — MCP Server:

Review mcp/synapse_mcp.py (paste below):
[paste mcp/synapse_mcp.py]

Ensure:
- All tools have descriptive docstrings (the LLM reads these to decide when to call)
- query_knowledge, think, ingest_url, check_job_status, get_stats all present
- FastMCP 2.2.9 syntax correct
- Returns plain strings (not dicts) for all tools

Write the three IDE config files as complete JSON:

File 1: .cursor/mcp.json
{
  "mcpServers": {
    "synapseos": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp/synapse_mcp.py"],
      "env": { "SYNAPSE_BASE_URL": "http://localhost:8000", ... }
    }
  }
}

File 2: claude_desktop_config.json (for Claude Code)
Same structure, with OS-specific paths for Mac and Windows shown separately

File 3: Windsurf MCP config (show where in settings.json)

TASK PART B — Cloudflare Workers:

Review cloudflare/worker.ts and cloudflare/wrangler.toml (paste):
[paste both files]

Verify:
- SHA-256 hash includes BOTH body AND X-Tenant-ID (prevents cross-tenant cache leaks)
- stream:true requests bypass cache entirely
- Cache TTL uses env var CACHE_TTL with default 3600
- wrangler.toml has correct compatibility_date (2025 or later)

Write cloudflare/deploy.sh — complete deployment script:
#!/bin/bash
# Step 1: Install wrangler
# Step 2: Login (opens browser)
# Step 3: Create KV namespace, capture ID
# Step 4: Sed-replace KV ID in wrangler.toml
# Step 5: Set ORACLE_BACKEND secret
# Step 6: Deploy and print worker URL
# Step 7: Test cache HIT/MISS with curl

ACCEPTANCE CRITERIA MCP:
- python3 mcp/synapse_mcp.py starts without error
- Cursor loads the server (appears in MCP tools list)
- Typing "@SynapseOS query_knowledge what is HNSW" returns real answer

ACCEPTANCE CRITERIA EDGE:
- First request: X-Cache: MISS, Oracle ARM logs show request
- Second identical request: X-Cache: HIT, response time < 50ms
- Streaming requests always bypass cache

OUTPUT: Fixed synapse_mcp.py + 3 IDE config files + fixed worker.ts + deploy.sh
```

---

## PHASE 4 — Cognitive Engine

---

### SESSION TASK — Day 6: Memory + Reflection

```
OBJECTIVE: SynapseOS remembers users across sessions. Answers self-improve via reflection. Both verified.

CONTEXT: Core RAG working. Now adding L7 cognitive capabilities.

TASK PART A — mem0 Memory:

Search the web for "mem0 python qdrant backend configuration 2025" to get current config format.

Review src/cognitive/memory.py (paste):
[paste src/cognitive/memory.py]

Ensure:
- mem0 LLM config uses Groq (groq provider, llama-3.1-8b-instant)
- Qdrant collection = "synapse_memory" (not synapse_knowledge)
- Embedder = fastembed BAAI/bge-base-en-v1.5
- history_db_path from DATABASE_URL env var (strip "+asyncpg")
- load_session() reads alternating role/content from KeyDB list
- append_session() sets 86400s TTL
- write_memory() in try/except — never raises

Write scripts/test_memory.py:
Step 1: write_memory("rahul", "test", [
  {"role":"user","content":"My name is Rahul. I run SR Creative Hub, a digital marketing agency in Bangladesh."},
  {"role":"assistant","content":"Got it, I'll remember that."}
])
Print "Memory written"
Sleep 2 seconds

Step 2: memories = load_memories("rahul", "test", "what is my name and business?")
Print recalled memories
PASS if "Rahul" in memories AND "SR Creative Hub" in memories
Print "✅ Memory recalled across sessions" or "❌ Memory not recalled"

Step 3: Verify synapse_memory collection has vectors
Print vector count

TASK PART B — Self-Reflection:

Review src/cognitive/reflection.py (paste):
[paste src/cognitive/reflection.py]

Ensure:
- Uses groq/llama-3.1-8b-instant (fast, ~200ms)
- Prompt requests JSON: {relevancy, faithfulness, completeness, critique}
- JSON parse in try/except (return original if parse fails)
- combined = 0.4*faithfulness + 0.3*relevancy + 0.3*completeness
- HARD LIMIT: max 1 retry, never loops

Write scripts/test_reflection.py:
context = "SynapseOS uses Qdrant for vector storage and Groq for LLM routing on Oracle ARM."

Case A: Good answer → expect NO retry:
  answer="SynapseOS uses Qdrant for vectors and Groq for LLM."
  Print scores + retry=No
  PASS if combined >= 0.7 and retry = False

Case B: Vague → expect retry + improvement:
  answer="SynapseOS uses modern technologies."
  Print original scores + improved answer
  PASS if retry = True and improved answer mentions Qdrant

Case C: Hallucinated → expect retry + correction:
  answer="SynapseOS uses Pinecone and OpenAI GPT-4."
  Print faithfulness score (expect < 0.4)
  PASS if retry = True

Print: "X/3 reflection cases correct"

ACCEPTANCE CRITERIA:
- test_memory.py: PASS on both Rahul AND SR Creative Hub
- test_reflection.py: 3/3 cases correct
- /v1/query response includes reflection_scores with combined > 0

OUTPUT: Fixed memory.py + fixed reflection.py + test_memory.py + test_reflection.py
```

### SESSION TASK — Day 7: Tool Executor

```
OBJECTIVE: All 4 built-in tools working. LiteLLM function calling routes to correct tool.

CONTEXT: Memory and reflection working. Adding tool use to cognitive engine.

TASK:
Search the web for "LiteLLM function calling tool_calls groq 2025 python" for current API.
Search the web for "Crawl4AI async web search example 2025".

Review src/cognitive/tools.py and src/core/generation.py (paste both):
[paste src/cognitive/tools.py]
[paste src/core/generation.py]

Ensure tools.py:
- retrieve_knowledge: calls hybrid_query, joins chunks with "\n\n", returns string
- web_search: Crawl4AI with page_timeout=15000, caps at 3000 chars, uses search URL
- calculate: whitelist chars only: 0-9 + - * / ( ) . space — rejects ALL others
- call_api: asyncpg fetch, Fernet decrypt, httpx.AsyncClient(timeout=15), caps at 3000 chars

Ensure generation.py has generate_with_tools():
- LiteLLM acompletion with tools= and tool_choice="auto"
- Parallel execution: asyncio.gather(*[executor.execute(tc.function.name, ...) for tc in tool_calls])
- Returns (final_answer: str, tools_used: list[str])

Write scripts/test_tools.py:

Test 1: web_search("Qdrant vector database python documentation")
  Print first 300 chars | PASS if non-empty and no error

Test 2: calculate("(42 * 1.5) + 10")
  Print result | PASS if result == "73.0"

Test 3: calculate("__import__('os').system('ls -la')")
  Print result | PASS if "Error: unsafe" in result

Test 4: calculate("1/0")
  Print result | PASS if "Error" in result (ZeroDivisionError caught)

Test 5: retrieve_knowledge("HNSW indexing Qdrant")
  Print first 200 chars | PASS if non-empty

Test 6: generate_with_tools() end-to-end
  question = "Search for the current Qdrant Python client version"
  Verify it calls web_search tool automatically
  Print: tools_used, answer snippet | PASS if "web_search" in tools_used

Print: "X/6 tool tests passed"

ACCEPTANCE CRITERIA:
- 6/6 tests pass
- calculate safety check MUST pass (injection blocked)
- generate_with_tools auto-selects correct tool without being told which to use

OUTPUT: Fixed tools.py + fixed generation.py + test_tools.py
```

### SESSION TASK — Day 8: /v1/think — Full Cognitive Engine

```
OBJECTIVE: POST /v1/think routes queries intelligently through memory + reasoning + tools + reflection. All 3 query types verified.

CONTEXT: Memory, reflection, tools all working from Days 6-7. Final integration.

TASK:
Search web for "DSPy ReAct module python 2025 chain of thought" for current API.

Review src/cognitive/engine.py and src/cognitive/planner.py (paste):
[paste src/cognitive/engine.py]
[paste src/cognitive/planner.py]

Ensure engine.py:
Step 1: asyncio.gather(load_session(), load_memories()) — parallel, never sequential
Step 2: classify_query() — uses groq/llama-3.1-8b-instant, defaults to "simple" on failure
Step 3a simple: hybrid_query → generate → reflect
Step 3b complex: hybrid_query with enriched context (session + memory + chunks) → generate → reflect, steps=2
Step 3c tool: generate_with_tools with BUILTIN_SCHEMAS → reflect, tools_used captured
Step 4: reflect_and_refine() on all paths
Step 5: asyncio.create_task(write_memory()) — NEVER await, fire-and-forget
Step 5: asyncio.create_task(append_session()) × 2 — user and assistant turns

Ensure planner.py:
- classify_query() uses fast_complete() which calls groq/llama-3.1-8b-instant
- Returns "simple", "complex", or "tool" — nothing else
- Defaults to "simple" if response is unexpected
- SynapseReAct available (DSPy module, may be unused in basic path)

Write scripts/test_think.py:

Setup: Assume memory from Day 6 test has "Rahul" and "SR Creative Hub" stored.

Test A — Simple retrieval:
  POST /v1/think {question:"what is HNSW graph indexing?", session_id:"think-A", user_id:"rahul"}
  PASS if query_type=="simple" AND answer mentions HNSW

Test B — Memory recall:
  POST /v1/think {question:"what is my name and business?", session_id:"think-B", user_id:"rahul"}
  PASS if memories_recalled >= 1 AND "Rahul" in answer

Test C — Tool use:
  POST /v1/think {question:"search the web for latest Qdrant Python client changelog 2025", session_id:"think-C", user_id:"rahul"}
  PASS if query_type=="tool" AND "web_search" in tools_used

Test D — Reflection always runs:
  Any question
  PASS if reflection_scores has faithfulness, relevancy, completeness, combined

Test E — Memory is written after response:
  After Test A, wait 2 seconds
  Call load_memories("rahul", "test", "HNSW") 
  PASS if memory was stored (vector count increased)

Print: "X/5 cognitive tests passed"

Write the final demo curl command as a bash script: scripts/demo.sh
It runs /v1/think with a rich question and pretty-prints the JSON response.

ACCEPTANCE CRITERIA:
- 5/5 tests pass
- /v1/think responds in < 3 seconds for simple path
- Memory writes never block the response (fire-and-forget confirmed)
- reflection_scores present on every response

OUTPUT: Fixed engine.py + fixed planner.py + test_think.py + scripts/demo.sh
```

---

## PHASE 5 — SvelteKit Widget (AgencyOS Integration)

---

### SESSION TASK — Day 9: SvelteKit Chat Widget

```
OBJECTIVE: SynapseOS embedded in SvelteKit as streaming chat widget. Works in AgencyOS.

CONTEXT: All API endpoints live. TypeScript SDK ready. Building UI layer.

TASK:
Search web for "SvelteKit SSE streaming server endpoint 2025" for current patterns.
Search web for "shadcn-svelte latest components 2025" for available components.

Write src/lib/components/RAGChatWidget.svelte — complete Svelte component:

Features required:
- Imports SynapseOSClient from '@synapseos/sdk'
- Gets config from: VITE_SYNAPSE_URL, VITE_SYNAPSE_KEY, VITE_TENANT_ID env vars
- Streaming: tokens appear in real time (requestAnimationFrame for smooth rendering)
- Typing indicator (animated dots) while waiting for first token
- Text input at bottom + Send button + Enter key triggers send
- Auto-scroll to bottom as tokens arrive
- Each assistant message shows: answer text + collapsible Sources section
- Sources show: source_url if available, truncated chunk text, score
- Thumbs up (👍) Thumbs down (👎) on each completed answer
  - On click: call client.feedback(trace_id, rating)
  - Visual confirmation: filled icon after click
- "Think" toggle switch: uses /v1/think instead of /v1/query when enabled
  - Shows: query_type badge, memories_recalled count, tools_used list
- Copy button on each answer
- Error state: shows "Something went wrong, try again" with retry button
- Uses Tailwind CSS utility classes only
- Minimal, clean dark theme default

Write src/routes/api/rag/+server.ts — SvelteKit SSE proxy:
- POST {question, session_id?, user_id?, use_think: bool}
- Reads SYNAPSE_URL + SYNAPSE_KEY from $env/static/private
- X-Tenant-ID from session or request header
- Streams SSE to browser (prevents CORS, hides API key)
- Sets: Content-Type: text/event-stream, Cache-Control: no-cache

Write src/lib/synapseos.ts — config and client singleton:
- Exports getSynapseClient() that returns cached SynapseOSClient instance
- Reads env vars at module level
- TypeScript strict mode compatible

Write integration guide as docs/svelte-integration.md:
5 steps to add widget to any SvelteKit page
Include the +page.svelte example

ACCEPTANCE CRITERIA:
- Widget renders without errors
- Streaming tokens appear in real time
- Thumbs up/down submits feedback
- Think mode toggle works
- Sources section shows correctly
- SSE proxy hides API key from browser

OUTPUT: RAGChatWidget.svelte + +server.ts + synapseos.ts + svelte-integration.md
```

---

## ONGOING — Nightly Optimizer

---

### SESSION TASK — Day 10: RAGAS Scoring + DSPy Optimization

```
OBJECTIVE: Nightly job scores interaction logs, exports training datasets, runs DSPy prompt optimization.

CONTEXT: All API endpoints running. interaction_logs being populated from /v1/query and /v1/think calls.

TASK:
Search web for "RAGAS evaluate dataset no ground truth reference-free 2025".
Search web for "DSPy MIPROv2 compile example 2025".

Review src/worker/nightly_optimizer.py (paste):
[paste src/worker/nightly_optimizer.py]

Write complete implementation of score_and_export():

1. FETCH: asyncpg query for unscored logs:
   SELECT id, tenant_id, query, answer, contexts FROM interaction_logs
   WHERE ragas_combined IS NULL AND dataset_exported = FALSE
   LIMIT 100 (process in batches to avoid OOM)

2. SCORE: For each log, run RAGAS:
   from ragas import evaluate
   from ragas.metrics import faithfulness, answer_relevancy, context_precision
   dataset = Dataset.from_list([{question, answer, contexts}])
   result = evaluate(dataset, metrics=[...])
   combined = 0.4*f + 0.3*ar + 0.3*cp

3. UPDATE: Write scores back to PostgreSQL:
   UPDATE interaction_logs SET ragas_faithfulness=$1, ... WHERE id=$2

4. EXPORT SFT: Logs with combined >= 0.7
   ChatML format: {"messages":[{"role":"system",...},{"role":"user",...},{"role":"assistant",...}]}
   Stream to MinIO: s3://synapseos/datasets/v{YYYYMMDD}/sft_train.jsonl

5. EXPORT DPO: For same questions, pair best vs worst response
   {"prompt":[...],"chosen":[...],"rejected":[...]}
   Stream to MinIO: .../dpo_train.jsonl

6. DSPy OPTIMIZATION (runs only if >= 50 new high-quality examples):
   Load gold_data = logs with combined >= 0.85
   Run SynapseRAG MIPROv2 with auto="light", max_bootstrapped_demos=3
   Save optimized prompt to /tmp/optimized_prompt.json
   Upload to MinIO: s3://synapseos/prompts/optimized_{date}.json

7. MARK EXPORTED: UPDATE interaction_logs SET dataset_exported=TRUE WHERE id IN (...)

Write scripts/test_nightly.py:
- Insert 5 fake interaction logs into PostgreSQL (mix of good and bad scores)
- Run score_and_export() manually
- Verify: scores updated in DB, JSONL files created in MinIO
- Print: logs scored, SFT examples, DPO pairs, optimization ran (Y/N)

ACCEPTANCE CRITERIA:
- No memory errors on ARM (batch processing, streaming MinIO upload)
- SFT JSONL is valid ChatML format readable by Unsloth
- DPO JSONL has proper chosen/rejected structure
- APScheduler runs at 02:00 UTC without interfering with request handling

OUTPUT: Complete nightly_optimizer.py + test_nightly.py
```

---

## EMERGENCY PROMPTS

### Any Python Error
```
I got this error:
[paste complete traceback]

This file caused it:
[paste the file]

ARM deployment context: Oracle ARM 4 vCPU 24GB no GPU.
Identify root cause. Fix it. Show complete corrected file.
Verify your fix doesn't introduce new issues.
```

### Docker Service Won't Start
```
Service [name] keeps restarting. Logs:
[paste: docker compose logs --tail=50 servicename]

My docker-compose.yml section for this service:
[paste the service block]

Diagnose. Fix the docker-compose.yml or config file.
Show exactly what to change with the corrected lines.
ARM note: this is Oracle ARM A1, not x86.
```

### Import / Package Error on ARM
```
I'm getting this import error on Oracle ARM Ubuntu 22.04:
[paste error]

Package: [name and version]
Python: 3.11

Search for the correct ARM-compatible install command.
Some packages need: --extra-index-url or pre-built ARM wheels.
Show the exact pip install command that works.
```

### Output Cut Off Mid-File
```
continue
```

### Agent Forgot Stack
```
Reminder — locked stack for this project:
FastAPI | Qdrant 1.13.5 | fastembed bge-base-en-v1.5 768d | LiteLLM/Groq |
mem0ai | Crawl4AI | Docling | RAGAS | DSPy | Langfuse | KeyDB | MinIO
Oracle ARM 4 vCPU 24GB NO GPU.
OMP_NUM_THREADS=4. Batch 64/16. Rerank max 15. KeyDB AOF no RDB.
Complete files only.
```

### Verify a File Before Using It
```
Before I copy this to my repo, verify this file:
[paste the file]

Check:
1. All imports are present and correct
2. No syntax errors
3. ARM constraints respected (OMP_NUM_THREADS, batch sizes, etc.)
4. No hardcoded secrets
5. All async functions properly awaited
6. tenant_id filter in every Qdrant query

List any issues. If clean: say "✅ File verified, safe to use."
```

---

## DAILY GIT COMMIT

Run at end of every session:
```bash
cd ~/synapseos
git add -A
git commit -m "day N: [what was built]

Changes:
- [file 1]: [what changed]
- [file 2]: [what changed]
Tests: [test command] → PASS"
git push origin main
```

Then append to AGENTS.md:
```markdown
## Session YYYY-MM-DD — Day N: [feature]
- Built: [description]
- Files changed: [list]
- Test command: [command]
- Status: ✅ done / ⚠️ partial / ❌ blocked
- Next: Day N+1 — [what to build]
```
