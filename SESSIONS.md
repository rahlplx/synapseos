# SynapseOS — Daily Build Sessions

> chat.z.ai free web app. Multiple prompts per day. Small, focused, sequential.
> Each prompt = one specific task. Paste → get output → copy to repo → next prompt.

---

## How This Works

```
Day starts → Open chat.z.ai → New Chat
Prompt 1   → Orientation (paste MINI-CONTEXT)
Prompt 2   → Main build task
Prompt 3   → Test/verify
Prompt 4   → Fix issues if any
Day ends   → Push to GitHub → log in AGENTS.md
```

**Rules:**
- New chat every day — never continue yesterday
- One prompt at a time — wait for full response before next
- If output cuts off → type: `continue`
- If confused → paste MINI-CONTEXT again
- Drag files into chat instead of typing them
- Always say: `Full file. No truncation. No ellipsis.`

**When daily limit hits:** switch to deepseek.com or claude.ai — same prompts work.

---

## MINI-CONTEXT — Paste at Start of Every Chat

```
You are helping me build SynapseOS — a self-improving BYOK RAG platform.

LOCKED STACK (never suggest alternatives):
FastAPI + Uvicorn | Qdrant 1.13.5 | fastembed BAAI/bge-base-en-v1.5 768d |
LiteLLM → Groq (primary) → OpenRouter → Anthropic | mem0ai |
Crawl4AI | Docling | RAGAS 0.2.15 | DSPy 2.5.20 | Langfuse v3 |
KeyDB | MinIO | Cloudflare Workers | Coolify on Oracle ARM 4vCPU/24GB NO GPU

ARM RULES — never break:
- OMP_NUM_THREADS=4 always for ONNX
- batch_size=64 ingestion, batch_size=16 query embedding  
- Cross-encoder input max=15 docs
- KeyDB: appendonly yes + save "" (AOF only, NO RDB)
- Docling: concurrency=1
- Qdrant: on_disk=True, memmap_threshold_kb=50000

REPO: github.com/rahlplx/synapseos
I am non-technical. Always give me COMPLETE files I copy directly to repo.
No snippets. No ellipsis. No "add the rest yourself." Full files only.
```

---

# PHASE 1 — Core RAG Engine

---

## DAY 1 — Docker: All Services Running

### Prompt 1.1 — Understand What You're Setting Up
```
I have a GitHub repo at github.com/rahlplx/synapseos.
It is a Python RAG platform with these Docker services:
Qdrant, PostgreSQL, KeyDB, MinIO, LiteLLM, FastAPI, Langfuse.

The server is Oracle ARM Ubuntu 22.04, 4 vCPU, 24GB RAM.
I will SSH into it to run commands.

First tell me:
1. Do I need to install anything on the server before starting? (Docker, Git, etc.)
2. What is the exact order to bring up services correctly?
3. What should I check to know everything is healthy?

Keep it short. Just the overview before we start.
```

### Prompt 1.2 — Server Prerequisites
```
Show me the exact commands to run on a fresh Oracle ARM Ubuntu 22.04 server to:
1. Install Docker Engine (not Docker Desktop)
2. Install Docker Compose plugin
3. Install Git
4. Add my user to the docker group so I don't need sudo
5. Verify all three are installed correctly

Copy-paste ready commands only. No explanation needed.
```

### Prompt 1.3 — Clone and Configure
```
My repo is at: https://github.com/rahlplx/synapseos

Give me exact commands to:
1. Clone the repo to /home/ubuntu/synapseos
2. cd into it
3. Copy .env.example to .env
4. Open .env with nano

Then list EVERY value in .env I need to fill, one by one:
- What it is
- Where to get it (Groq free key at console.groq.com, etc.)
- Example format

Do not skip any values.
```

### Prompt 1.4 — Start Services and Verify
```
I have filled my .env file. Now give me:

1. Command to start all services: docker compose up -d
2. Command to check all containers are running: docker compose ps
3. Command to check each service health individually:
   - Qdrant health
   - PostgreSQL health  
   - KeyDB health
   - MinIO health
   - LiteLLM health
   - Langfuse health (opens in browser)
4. What to do if a container shows as "Exit" or "unhealthy"
5. How to view logs for a specific service that has problems

Give me exact commands with expected output for each.
```

### Prompt 1.5 — Initialize Database and Buckets
```
All containers are running. Now I need to initialize:

1. Run the SQL init script to create all tables:
   Show exact command to run scripts/init-db.sql against the postgres container

2. Run the MinIO bucket setup:
   Show exact command to run scripts/init-minio.sh

3. Verify both worked:
   - How to check tables exist in PostgreSQL
   - How to check the synapseos bucket exists in MinIO (browser at port 9001)

Give exact commands for all three steps.
```

**Day 1 done when:** `docker compose ps` shows all containers Up, database tables exist, MinIO bucket exists.

---

## DAY 2 — Qdrant Collection + First Ingest

### Prompt 2.1 — Review Ingestion Code
```
I have these two files in my repo. I will drag them into this chat now.

[drag src/core/ingestion.py]
[drag src/core/retrieval.py]

Review both files specifically for Oracle ARM issues:
1. Is OMP_NUM_THREADS=4 set correctly?
2. Is batch_size=64 for ingestion and batch_size=16 for queries?
3. Is Docling CPU-only mode set?
4. Is the Qdrant connection pointing to the right host?
5. Is SHA-256 dedup working correctly?

List any issues found. Do not fix yet — just list them.
```

### Prompt 2.2 — Fix Ingestion Files
```
Fix all issues you found. Show me:

1. Complete corrected src/core/ingestion.py
   Full file. No truncation.

2. Complete corrected src/core/retrieval.py
   Full file. No truncation.

I will copy both files exactly into my repo.
```

### Prompt 2.3 — Collection Setup Script
```
Write a complete standalone Python script: scripts/setup_collection.py

It must:
1. Connect to Qdrant at http://localhost:6333
2. Create collection named "synapse_knowledge" if it doesn't exist:
   - Dense vector: 768d, cosine, on_disk=True
   - Sparse vector: Qdrant/bm25 with IDF modifier
   - memmap_threshold_kb=50000
   - max_segment_size_kb=65536
3. Create payload index on "tenant_id" field (keyword type)
4. Also create "synapse_memory" collection for mem0 (same settings)
5. Print confirmation for each step

Full file. I run it with: python3 scripts/setup_collection.py
```

### Prompt 2.4 — First Ingest Test
```
Write a complete standalone Python script: scripts/test_ingest.py

It must:
1. Run setup_collection() to ensure collections exist
2. Ingest this URL: https://qdrant.tech/documentation/concepts/
   Using tenant_id = "test"
3. Print progress: "Scraping..." → "Parsing..." → "Chunking..." → "Embedding..." → "Storing..."
4. Print final results:
   - Number of chunks stored
   - Total time taken in seconds
   - RAM used (import psutil)
5. Query Qdrant to verify vectors exist: print vector count for tenant "test"

Full file. No imports left undefined. Run with: python3 scripts/test_ingest.py
```

### Prompt 2.5 — Run and Debug
```
I ran: python3 scripts/test_ingest.py

[paste your actual terminal output here]

If there are errors, diagnose and fix them.
Show me the exact corrected file to replace.

If it succeeded, tell me:
1. How to verify in Qdrant dashboard (port 6333) that vectors exist
2. The exact URL to open in browser
3. What to look for in the Collections section
```

**Day 2 done when:** test_ingest.py completes without errors, vectors visible in Qdrant dashboard.

---

## DAY 3 — Hybrid Query Working

### Prompt 3.1 — Understand Hybrid Retrieval
```
[drag src/core/retrieval.py into chat]

Walk me through what hybrid_query() does step by step:
1. What is dense retrieval doing?
2. What is sparse BM25 doing?
3. What is RRF fusion doing?
4. What is the cross-encoder doing?
5. Why is the cap at 15 docs before cross-encoder important on ARM?

Plain English. No code yet.
```

### Prompt 3.2 — Fix hybrid_query
```
Review hybrid_query() in my retrieval.py for these specific issues:
1. Are both dense and sparse vectors being generated separately?
2. Is the Qdrant Query API using prefetch correctly for both?
3. Is RRF fusion (models.Fusion.RRF) applied after prefetch?
4. Is cross-encoder input capped at 15 docs (rerank_k=15)?
5. Is tenant_id filter applied in BOTH prefetch queries?
6. Is the final result returning only hits with score > 0.1?

Fix every issue. Show me the complete corrected retrieval.py.
Full file. No truncation.
```

### Prompt 3.3 — Retrieval Test Script
```
Write a complete standalone Python script: scripts/test_retrieval.py

It must:
1. Run hybrid_query("how does HNSW graph indexing work?", tenant_id="test")
2. Time each phase separately using time.perf_counter():
   - Phase A: Generate dense + sparse embeddings
   - Phase B: Qdrant search (prefetch + RRF)
   - Phase C: Cross-encoder reranking
   - Total end-to-end
3. Print top 5 results with:
   - Chunk number (1-5)
   - Cross-encoder score
   - First 150 characters of text
4. Print latency summary:
   Phase A: Xms | Phase B: Xms | Phase C: Xms | Total: Xms
   Target: Total under 400ms

Full standalone file. All imports included.
```

### Prompt 3.4 — Also Test Dense-Only vs Hybrid
```
Add a comparison to scripts/test_retrieval.py:

After the hybrid query, run the same question using dense-only search.
Compare results:
- Did hybrid find different/better chunks than dense-only?
- Show side-by-side top 3 results from each

This proves hybrid retrieval is actually better.
Show me the complete updated scripts/test_retrieval.py.
```

### Prompt 3.5 — Run and Interpret Results
```
I ran: python3 scripts/test_retrieval.py

[paste your actual output here]

Tell me:
1. Is the latency acceptable? (under 400ms total is good for ARM)
2. Are the chunks relevant to the question?
3. Did hybrid outperform dense-only?
4. Are there any warnings or issues to fix?

If latency is over 400ms, tell me which phase to optimize and how.
```

**Day 3 done when:** hybrid query returns relevant chunks under 400ms P95.

---

## DAY 4 — /v1/query Endpoint Live

### Prompt 4.1 — Review API Files
```
I have four files to show you. Dragging them now:

[drag src/api/main.py]
[drag src/api/routes/query.py]
[drag src/api/middleware/tenant.py]
[drag src/core/generation.py]

Review all four together. Find issues with:
1. Does TenantMiddleware run BEFORE the route? (order in main.py matters)
2. Does it read GROQ_API_KEY from environment correctly?
3. Does query.py call hybrid_query then generate correctly?
4. Is SSE streaming format correct: data: {"chunk": "text"}\n\n ?
5. Is the LiteLLM fallback chain set up (Groq → OpenRouter → Anthropic)?
6. Will it handle a request without BYOK key (use platform Groq key)?

List all issues found.
```

### Prompt 4.2 — Fix and Show Complete Files
```
Fix all issues. Show me each complete file separately:

First: src/api/middleware/tenant.py
(full file, no truncation)

Then wait for me to say "next" before showing the next file.
```

### Prompt 4.3 — Next Files
```
next
```
*(repeat this pattern for each file: query.py, generation.py, main.py)*

### Prompt 4.4 — Start Server and Test
```
How do I:
1. Install dependencies: pip install -r requirements.txt
   (is there anything that installs differently on ARM?)
2. Start the FastAPI server:
   uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
3. Verify it started (what to look for in terminal output)
4. Test with curl:

Give me the exact curl command to test /v1/query with:
- X-Tenant-ID: test
- question: "how does HNSW indexing work?"
- stream: true

Show expected output format (what the streaming chunks look like).
```

### Prompt 4.5 — Debug Any Errors
```
I started the server and ran the curl command.

[paste your terminal output and curl output here]

Diagnose any errors and give me exact fixes.
Show complete corrected files where needed.
```

### Prompt 4.6 — Verify End-to-End
```
The server is running and curl works. Now write a quick end-to-end test:
scripts/test_endpoint.py

It must:
1. Use httpx to POST to http://localhost:8000/v1/query
2. Headers: X-Tenant-ID: test, Content-Type: application/json
3. Body: question = "what is Qdrant?", stream = false
4. Print the full answer
5. Print: status code, latency in ms
6. Assert answer is not empty and status is 200

Run with: python3 scripts/test_endpoint.py
Full file.
```

**Day 4 done when:** curl returns streaming Groq answer. Phase 1 complete.

---

# PHASE 2 — SDK + Edge

---

## DAY 5 — Python SDK

### Prompt 5.1 — Review SDK
```
[drag sdk/python/synapseos/client.py into chat]

Review AsyncSynapseClient for:
1. Does query() correctly handle non-streaming response?
2. Does query_stream() correctly parse SSE lines (data: prefix)?
3. Does ingest() return IngestJob with job_id?
4. Does feedback() send correct payload?
5. Are timeouts set appropriately (query=60s, stream=120s)?
6. Is error handling present for HTTP errors?

List all issues.
```

### Prompt 5.2 — Fix SDK
```
Fix all issues. Show complete corrected sdk/python/synapseos/client.py.
Full file. No truncation.
```

### Prompt 5.3 — SDK Test Script
```
Write complete scripts/test_sdk.py:

Prerequisites: pip install -e sdk/python/
API must be running at http://localhost:8000

Tests:
1. TEST query() — non-streaming
   client.query("what is Qdrant?")
   Print: answer text, PASS/FAIL

2. TEST query_stream() — streaming
   client.query_stream("explain BM25 in one sentence")
   Print each chunk as it arrives on same line
   Print: total chunks received, PASS/FAIL

3. TEST ingest() — queue ingestion
   client.ingest(["https://python.org"])
   Print: job_id returned, PASS/FAIL

4. TEST feedback() — submit rating
   client.feedback("test-trace-123", rating=1)
   Print: PASS/FAIL

Print final summary: X/4 tests passed
Full file. All imports included.
```

### Prompt 5.4 — Package Installation
```
Show me exactly how to:
1. Install the SDK locally for testing: pip install -e sdk/python/
2. Verify it installed: python3 -c "from synapseos import AsyncSynapseClient; print('OK')"
3. Run the test: python3 scripts/test_sdk.py

Also write sdk/python/synapseos/__init__.py correctly if it needs updating.
Show me the file.
```

**Day 5 done when:** all 4 SDK tests pass.

---

## DAY 6 — TypeScript SDK + SvelteKit Widget

### Prompt 6.1 — Review TypeScript SDK
```
[drag sdk/typescript/src/index.ts into chat]

Review SynapseOSClient TypeScript:
1. Does queryStream() correctly read SSE from a fetch ReadableStream?
2. Does it handle partial lines correctly (buffer + split on newline)?
3. Does it parse "data: " prefix correctly?
4. Does it stop on done:true payload?
5. Does feedback() send the right payload?
6. Are types correct (QueryResult, Source)?

List all issues.
```

### Prompt 6.2 — Fix TypeScript SDK
```
Fix all issues. Show complete sdk/typescript/src/index.ts.
Full file. No truncation.

Also show sdk/typescript/package.json — update if needed.
```

### Prompt 6.3 — SvelteKit Streaming Chat Widget
```
Write a complete SvelteKit chat widget component.

File: src/lib/components/RAGChatWidget.svelte

Requirements:
- Import SynapseOSClient from @synapseos/sdk (via npm link or env var base URL)
- Base URL from: import.meta.env.VITE_SYNAPSE_URL
- API key from: import.meta.env.VITE_SYNAPSE_KEY  
- Tenant ID from: import.meta.env.VITE_TENANT_ID
- Streaming: tokens appear word by word in real time
- Shows "Thinking..." with animated dots while streaming
- Text input at bottom, Send button, Enter key works
- Chat history scrolls automatically
- Shows source URLs under each answer (collapsible)
- Thumbs up (👍) and thumbs down (👎) on each answer
- Uses Tailwind CSS classes only (no custom CSS)
- Works with shadcn-svelte if available

Full file. Complete component. No truncation.
```

### Prompt 6.4 — SvelteKit SSE Proxy Route
```
Write the SvelteKit server endpoint that proxies SSE to avoid CORS:

File: src/routes/api/rag/+server.ts

It must:
- Accept POST with { question, session_id? }
- Read SYNAPSE_URL and SYNAPSE_KEY from SvelteKit env (private)
- Get tenant_id from session or request header
- Forward to SynapseOS /v1/query as SSE
- Re-stream SSE chunks back to browser
- Handle errors gracefully

Full file. Import types from @sveltejs/kit.
```

### Prompt 6.5 — Integration Instructions
```
Give me step-by-step instructions to add RAGChatWidget to an existing SvelteKit + AgencyOS project:

1. npm install command for the TypeScript SDK
2. .env variables to add
3. Where to import ChatWidget.svelte
4. How to drop it into a page: +page.svelte example
5. How to test it works

Keep it simple. 5 steps max.
```

**Day 6 done when:** widget renders in SvelteKit and streams a real answer.

---

## DAY 7 — MCP Server

### Prompt 7.1 — Review MCP Server
```
[drag mcp/synapse_mcp.py into chat]

Review synapse_mcp.py for FastMCP 2.2.9:
1. Are tool decorators @mcp.tool() correct syntax?
2. Does each tool have a clear docstring? (LLM uses this to decide when to call it)
3. Is the client pointing to correct base URL?
4. Does query_knowledge return a clean string (not a dict)?
5. Does ingest_url return useful confirmation?
6. Is the MCP server running on stdio (correct for IDE integration)?

List all issues.
```

### Prompt 7.2 — Fix and Add Tools
```
Fix all issues. Also add these two new tools:

1. check_job_status(job_id: str) -> str
   Checks if an ingestion job is done/processing/failed
   Returns human-readable status string

2. list_knowledge_stats() -> str
   Returns: vector count, document count, tenant info
   Formatted as readable text

Show complete corrected mcp/synapse_mcp.py. Full file.
```

### Prompt 7.3 — Installation Instructions
```
Show me exactly how to:
1. Install FastMCP: pip install fastmcp
2. Test MCP server runs: python3 mcp/synapse_mcp.py
   What should I see in terminal?
3. Set environment variables it needs before running
```

### Prompt 7.4 — IDE Config Files
```
Give me the complete config files to integrate SynapseOS MCP into each tool.
Show each as a complete file I copy exactly:

1. Cursor — file: .cursor/mcp.json
   (at project root OR at ~/.cursor/mcp.json globally)

2. Claude Code — file: claude_desktop_config.json
   (location: ~/Library/Application Support/Claude/ on Mac)
   (location: %APPDATA%/Claude/ on Windows)

3. Windsurf — show where and what to add in settings

For each: show the exact JSON with placeholder paths I fill in.
```

### Prompt 7.5 — Test MCP Integration
```
I installed the MCP server and configured Cursor.

Tell me:
1. How to verify Cursor picked up the MCP server
2. What to type in Cursor chat to trigger SynapseOS tools
3. What a successful response looks like
4. How to debug if Cursor shows "MCP server failed to start"
```

**Day 7 done when:** Claude Code or Cursor can call query_knowledge and get a real answer.

---

## DAY 8 — Cloudflare Workers Edge

### Prompt 8.1 — Review Worker
```
[drag cloudflare/worker.ts into chat]
[drag cloudflare/wrangler.toml into chat]

Review for issues:
1. Does the SHA-256 hash include X-Tenant-ID header? (must prevent cross-tenant cache pollution)
2. Does stream:true bypass the cache entirely?
3. Is the KV put() including expirationTtl?
4. Is the wrangler.toml pointing to the right entry file?
5. Are there any TypeScript type errors?

List all issues.
```

### Prompt 8.2 — Fix Worker Files
```
Fix all issues. Show:

1. Complete cloudflare/worker.ts — full file
2. Complete cloudflare/wrangler.toml — full file

No truncation.
```

### Prompt 8.3 — Deployment Steps
```
Show me exact step-by-step commands to deploy the Cloudflare Worker:

1. Install wrangler globally
2. Login to Cloudflare
3. Create KV namespace and get the namespace ID
4. Update wrangler.toml with the real namespace ID (show exactly what to replace)
5. Set ORACLE_BACKEND secret (my Oracle ARM API URL)
6. Deploy the worker
7. Get the deployed worker URL

Copy-paste commands. No skipped steps.
```

### Prompt 8.4 — Test Cache
```
The worker is deployed at: [my_worker_url]
My Oracle ARM API is at: [my_arm_url]

Write me two curl commands:

1. First request (should be MISS — goes to Oracle ARM):
   curl with all headers, show X-Cache response header

2. Identical second request (should be HIT — served from edge):
   Show expected < 50ms response time

Also tell me:
- How to check Cloudflare Analytics for cache hit rate
- How to clear the cache if needed (wrangler kv command)
```

**Day 8 done when:** second identical request shows X-Cache: HIT in under 50ms. Phase 2 complete.

---

# PHASE 3 — Cognitive Engine

---

## DAY 9 — Memory (mem0)

### Prompt 9.1 — Review Memory Module
```
[drag src/cognitive/memory.py into chat]

Review memory.py for issues:
1. Is mem0 config using Groq (not z.ai API)?
2. Is the Qdrant collection set to "synapse_memory" (separate from "synapse_knowledge")?
3. Is the embedder set to BAAI/bge-base-en-v1.5?
4. Is load_session() reading from KeyDB correctly (role, content alternating)?
5. Is append_session() setting 24h TTL?
6. Is write_memory() wrapped in try/except so it never blocks response?

List all issues.
```

### Prompt 9.2 — Fix Memory Module
```
Fix all issues. Show complete corrected src/cognitive/memory.py.
Full file. No truncation.

Also: if mem0ai has any known ARM installation issues (like missing native deps),
tell me the exact pip install command that works on Oracle ARM Ubuntu 22.04.
```

### Prompt 9.3 — Memory Test Script
```
Write complete scripts/test_memory.py:

This test proves memory works ACROSS separate sessions (not just in same context).

Step 1 — First conversation:
  session_id = "test-session-A"
  user_id = "rahul"
  Append to session: user said "My name is Rahul. I run a digital marketing agency in Bangladesh."
  Call write_memory() to extract and store facts
  Print: "Facts stored. Waiting..."
  Sleep 2 seconds

Step 2 — Second conversation (simulated new chat):
  session_id = "test-session-B" (completely different session)
  user_id = "rahul" (same user)
  question = "What is my name and what do I do for work?"
  Call load_memories("rahul", "test", question)
  Print the recalled memories
  Print whether the answer would include name and job (yes/no)

Step 3 — Verify in Qdrant:
  Query synapse_memory collection for user rahul
  Print vector count found

Run with: python3 scripts/test_memory.py
Full file.
```

### Prompt 9.4 — Wire Memory into /v1/think Route
```
Show me how to update src/api/routes/think.py to:
1. Accept session_id and user_id in the request body
2. Call load_session() and load_memories() at start (in parallel with asyncio.gather)
3. Pass memory context into the generation
4. Call write_memory() at end as asyncio.create_task() (non-blocking)

Show complete updated src/api/routes/think.py. Full file.
```

**Day 9 done when:** test_memory.py proves facts recalled in a different session.

---

## DAY 10 — Self-Reflection

### Prompt 10.1 — Review Reflection Module
```
[drag src/cognitive/reflection.py into chat]

Review reflect_and_refine() for issues:
1. Is Groq Llama-8b used as judge? (fast, ~200ms)
2. Is the reflection prompt asking for JSON output?
3. Is JSON parsing wrapped in try/except (malformed JSON should not crash)?
4. Is the combined score formula: 0.4*faithfulness + 0.3*relevancy + 0.3*completeness?
5. Is there a hard limit of 1 retry maximum?
6. Does it return the original answer if reflection itself fails?

List all issues.
```

### Prompt 10.2 — Fix Reflection Module
```
Fix all issues. Show complete corrected src/cognitive/reflection.py. Full file.
```

### Prompt 10.3 — Reflection Test Script
```
Write complete scripts/test_reflection.py:

Setup: define a fake context = "SynapseOS uses Qdrant for vector storage and Groq for LLM routing."

Test Case A — Good answer:
  answer = "SynapseOS uses Qdrant for vectors and Groq for LLM routing."
  question = "What does SynapseOS use?"
  Expected: score >= 0.70, no retry triggered
  Print: scores, retry=No

Test Case B — Vague answer:
  answer = "SynapseOS uses various technologies."
  question = "What does SynapseOS use?"
  Expected: score < 0.70, retry triggered, improved answer returned
  Print: original scores, retry=Yes, improved answer

Test Case C — Hallucinated answer:
  answer = "SynapseOS uses Pinecone for vectors and OpenAI for LLM."
  question = "What does SynapseOS use?"
  Expected: score very low, retry triggered, corrected answer
  Print: original scores, retry=Yes, corrected answer

Run with: python3 scripts/test_reflection.py
Full file. Uses fast_complete() from src/core/generation.py.
```

### Prompt 10.4 — Add Reflection to /v1/query
```
Update src/api/routes/query.py to:
1. After generate() returns an answer, call reflect_and_refine()
2. Return the final (possibly improved) answer
3. Add reflection_scores to the response JSON
4. Add "retried": true/false to response JSON

Show complete updated src/api/routes/query.py. Full file.
```

### Prompt 10.5 — Verify Reflection in API Response
```
Show me a curl command to test /v1/query that shows reflection scores in response:

curl -X POST http://localhost:8000/v1/query \
  -H "X-Tenant-ID: test" \
  -H "Content-Type: application/json" \
  -d '{"question":"what does SynapseOS use for vector storage?","stream":false}'

Expected response JSON structure (show me what it should look like now with reflection_scores).
```

**Day 10 done when:** /v1/query response includes reflection_scores and answers are better quality.

---

## DAY 11 — Tool Use

### Prompt 11.1 — Review Tools Module
```
[drag src/cognitive/tools.py into chat]

Review ToolExecutor for each tool:

retrieve_knowledge:
- Does it call hybrid_query correctly?
- Is tenant_id passed through?

web_search:
- Does it use Crawl4AI with 15 second timeout?
- Does it cap output at 3000 chars?

calculate:
- Does it only allow: 0-9, +, -, *, /, (, ), ., space?
- Does it reject anything else before eval()?

call_api:
- Is Fernet decryption correct?
- Is httpx timeout set?

List all issues.
```

### Prompt 11.2 — Fix Tools Module
```
Fix all issues. Show complete corrected src/cognitive/tools.py. Full file.
```

### Prompt 11.3 — Add Function Calling to Generation
```
[drag src/core/generation.py into chat]

Add this new async function to generation.py:

async def generate_with_tools(
    question: str,
    context: str,
    tools: list[dict],
    tenant_api_key: str = None
) -> tuple[str, list[str]]:
    # 1. Call Groq with tool schemas via LiteLLM function calling
    # 2. If tool_calls in response: execute all in parallel with asyncio.gather
    # 3. Append tool results to messages
    # 4. Get final answer
    # Returns: (final_answer, list_of_tool_names_used)

The tools parameter is a list of OpenAI function schemas.
Use GENERATION_MODEL (Groq 70b) — Groq supports function calling.

Show complete updated src/core/generation.py. Full file.
```

### Prompt 11.4 — Tools Test Script
```
Write complete scripts/test_tools.py:

Test 1 — web_search:
  executor.execute("web_search", {"query": "Qdrant vector database 2025"}, "test")
  Print: first 500 chars of result, time taken
  Pass if result is non-empty

Test 2 — calculate:
  executor.execute("calculate", {"expression": "(42 * 1.5) + 10"}, "test")
  Print: result
  Pass if result == "73.0"

Test 3 — calculate safety:
  executor.execute("calculate", {"expression": "__import__('os').system('ls')"}, "test")
  Print: result
  Pass if result starts with "Error: unsafe"

Test 4 — retrieve_knowledge:
  executor.execute("retrieve_knowledge", {"query": "what is HNSW"}, "test")
  Print: first chunk returned
  Pass if result is non-empty

Print: X/4 tests passed
Full file.
```

**Day 11 done when:** all 4 tool tests pass, especially calculate safety check.

---

## DAY 12 — /v1/think: Full Cognitive Engine

### Prompt 12.1 — Review Cognitive Engine
```
[drag src/cognitive/engine.py into chat]
[drag src/api/routes/think.py into chat]

Review cognitive_query() orchestrator step by step:

Step 1 Memory Load: are session and long-term memory loaded with asyncio.gather (parallel)?
Step 2 Classify: is classify_query() using fast_complete() which uses Groq?
Step 3 Execute: are all 3 paths (simple/complex/tool) implemented?
Step 4 Reflect: is reflect_and_refine() called on the answer?
Step 5 Memory Write: is write_memory() using asyncio.create_task() (non-blocking)?

List all issues in both files.
```

### Prompt 12.2 — Fix Engine and Route
```
Fix all issues.

Show complete corrected src/cognitive/engine.py. Full file. No truncation.

[wait for response, then:]

Show complete corrected src/api/routes/think.py. Full file. No truncation.
```

### Prompt 12.3 — Full Cognitive Test
```
Write complete scripts/test_think.py:

Prerequisites:
- API running at http://localhost:8000
- Vectors in Qdrant from Day 2
- mem0 memory set up from Day 9

Run three tests via httpx POST to /v1/think:

TEST A — Simple retrieval:
  question="What is HNSW graph indexing?"
  session_id="think-test-A", user_id="rahul"
  Expected: query_type = "simple"
  Print: query_type, answer, reflection_scores

TEST B — Memory recall:
  question="What is my name?"
  session_id="think-test-B", user_id="rahul"
  (Should recall "Rahul" from Day 9 memory)
  Expected: query_type = "simple", memories_recalled > 0
  Print: query_type, memories_recalled, answer

TEST C — Tool use:
  question="Search the web for Qdrant latest release"
  session_id="think-test-C", user_id="rahul"
  Expected: query_type = "tool", tools_used includes "web_search"
  Print: query_type, tools_used, answer

Print final: X/3 tests passed

Full file.
```

### Prompt 12.4 — End-to-End curl Test
```
Show me the complete curl command to test /v1/think that I can save as my permanent demo:

curl -X POST http://localhost:8000/v1/think \
  -H "X-Tenant-ID: test" \
  -H "Content-Type: application/json" \
  -d '[complete JSON body]'

Show expected full response JSON with all fields:
- answer
- query_type
- steps_taken
- reflection_scores
- memories_recalled
- tools_used

This is my Phase 3 completion test.
```

### Prompt 12.5 — Final Repo Commit
```
SynapseOS is complete. Give me the git commands to:
1. Add all changed files: git add -A
2. Write a commit message summarizing Phase 3 completion
3. Push to GitHub

Also give me a final checklist to verify everything works:
[ ] All Docker services up
[ ] /v1/query streams an answer
[ ] /v1/think uses memory + tools + reflection  
[ ] Python SDK tests pass
[ ] MCP server loads in Claude Code or Cursor
[ ] Cloudflare Worker caches requests
```

**Day 12 done when:** all 3 cognitive tests pass. SynapseOS is production-ready.**

---

## Quick Reference

### If output cuts off
```
continue
```

### If it forgets context
```
[paste MINI-CONTEXT again]
```

### If there's a Python error
```
I got this error:
[paste full traceback]

My current file:
[drag the file into chat]

Fix it. Show complete corrected file.
```

### If Docker service won't start
```
Service [name] is failing. Here are the logs:
[docker compose logs servicename]

Fix the docker-compose.yml or config file. Show what to change.
```

### Daily git commit (run after every day)
```bash
cd ~/synapseos
git add -A
git commit -m "day N: [what you built]"
git push origin main
```

### Session log for AGENTS.md
```markdown
## Session YYYY-MM-DD — Day N: [feature]
- Built: [description]
- Files changed: [list]
- Test command: [command]
- Status: ✅ complete / ⚠️ partial / ❌ blocked
- Next: Day N+1 — [what to build]
```
