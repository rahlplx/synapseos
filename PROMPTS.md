# SynapseOS — Complete Session Prompts

> Every prompt for every day. Copy-paste into chat.z.ai exactly as written.
> Start every new chat with the STARTER block first, then go prompt by prompt.

---

## STARTER — Paste This First in Every New Chat

```
You are helping me build SynapseOS — a self-improving BYOK RAG platform deployed on Oracle ARM.

LOCKED STACK (never suggest alternatives):
FastAPI 0.115 | Qdrant 1.13.5 | fastembed BAAI/bge-base-en-v1.5 768d |
LiteLLM → Groq (primary) → OpenRouter → Anthropic |
mem0ai | Crawl4AI | Docling | RAGAS 0.2.15 | DSPy 2.5.20 |
Langfuse v3 | KeyDB | MinIO | FastMCP 2.2.9 | Cloudflare Workers |
Coolify on Oracle ARM 4 vCPU / 24GB RAM — NO GPU

ARM RULES (never break):
- OMP_NUM_THREADS=4 before fastembed import
- batch_size=64 ingestion, batch_size=16 query
- cross-encoder input max = 15 docs
- KeyDB: appendonly yes + save "" (NO RDB, fork causes OOM)
- Qdrant: on_disk=True, memmap_threshold_kb=50000
- Docling: concurrency=1, DOCLING_CPU_ONLY=1
- LLM: groq/llama-3.1-70b-versatile generation, groq/llama-3.1-8b-instant fast tasks
- Collections: synapse_knowledge (RAG), synapse_memory (mem0)
- tenant_id filter on EVERY Qdrant query

I am non-technical. Give me COMPLETE files I paste directly into the repo.
No partial code. No ellipsis. No "add rest yourself". Full files always.
Reply "Ready" to confirm.
```

---

## DAY 1 — Docker: All Services Running

### Prompt 1-A
```
I have a fresh Oracle ARM server running Ubuntu 22.04.
I need to install Docker, Docker Compose, and Git.
Give me the exact commands to run in order.
Include: adding my user to docker group so I never need sudo.
Copy-paste ready. No explanation.
```

### Prompt 1-B
```
My repo is at https://github.com/rahlplx/synapseos
Give me exact commands to:
1. Clone it to /home/ubuntu/synapseos
2. cd into it
3. Copy .env.example to .env

Then list every single value in .env I need to fill:
- Variable name
- What it is
- Where to get it (exact URL if signup needed)
- Example format
Do not skip any variable.
```

### Prompt 1-C
```
I have filled my .env file. Now:
1. Command to start all services: docker compose up -d
2. Command to see if all containers are running
3. Exact command to check health of each service:
   - Qdrant (port 6333)
   - PostgreSQL
   - KeyDB
   - MinIO (port 9000 and 9001)
   - LiteLLM (port 4000)
   - Langfuse (port 3100)
4. What healthy output looks like for each
5. Most common startup error and how to fix it
```

### Prompt 1-D
```
All containers are running. Now initialize the database and storage:

1. Exact command to run scripts/init-db.sql against the postgres container
2. Exact command to run scripts/init-minio.sh
3. How to verify tables exist in PostgreSQL
4. How to open MinIO browser at port 9001 and confirm the synapseos bucket exists
5. How to open Langfuse at port 3100 and create an admin account

Step by step. Exact commands.
```

### Prompt 1-E
```
Run the healthcheck script and tell me what to do:
./scripts/healthcheck.sh

Expected output when everything is perfect — show me exactly what I should see.
If any service shows a red X, what is the most likely cause and fix?
```

---

## DAY 2 — Qdrant Collection + First Ingest

### Prompt 2-A
```
[drag src/core/ingestion.py into chat]
[drag src/core/retrieval.py into chat]

Check both files for Oracle ARM issues only:
1. Is OMP_NUM_THREADS=4 set before fastembed import?
2. Is batch_size=64 for ingestion and batch_size=16 for queries?
3. Is DOCLING_CPU_ONLY=1 set?
4. Is Qdrant host pointing to "qdrant" (Docker service name)?
5. Is SHA-256 dedup using KeyDB correctly?
6. Is on_disk=True in collection creation?

List every issue found. One line each.
```

### Prompt 2-B
```
Fix every issue you found in both files.

Show complete corrected src/core/ingestion.py first.
Full file. No truncation. No ellipsis.
```

### Prompt 2-C
```
Show complete corrected src/core/retrieval.py.
Full file. No truncation. No ellipsis.
```

### Prompt 2-D
```
Write a complete standalone Python script: scripts/setup_collection.py

It must do exactly this in order:
1. Connect to Qdrant at http://localhost:6333
2. Create collection "synapse_knowledge" if it does not exist:
   - Dense vector: size=768, distance=Cosine, on_disk=True
   - Sparse vector: Qdrant/bm25 with IDF modifier
   - optimizers: memmap_threshold_kb=50000, max_segment_size_kb=65536
3. Create payload index on "tenant_id" field (keyword type)
4. Create collection "synapse_memory" with same settings (for mem0)
5. Print "Collection ready: synapse_knowledge" and "Collection ready: synapse_memory"
6. Print total vector count for each collection

All imports included. Run with: python3 scripts/setup_collection.py
Full file.
```

### Prompt 2-E
```
Write a complete standalone Python script: scripts/test_ingest.py

It must do exactly this:
1. Import and run setup_collection() first to ensure collections exist
2. Ingest this URL: https://qdrant.tech/documentation/concepts/
   tenant_id = "test"
3. Print progress at each step:
   "Scraping URL..." then "Parsing markdown..." then "Chunking..."
   then "Deduplicating..." then "Embedding..." then "Storing in Qdrant..."
4. Print final results:
   - Chunks stored: X
   - Time taken: X.Xs
   - Memory used: XMB (use psutil)
5. Verify by querying Qdrant — print: "Vectors in Qdrant for tenant test: X"

All imports included. pip install psutil if needed.
Run with: python3 scripts/test_ingest.py
Full file. No truncation.
```

### Prompt 2-F
```
I ran: python3 scripts/setup_collection.py

Output:
[paste your actual output here]

Then I ran: python3 scripts/test_ingest.py

Output:
[paste your actual output here]

Did it work? Are there any issues?
How do I verify in the Qdrant web dashboard at http://localhost:6333/dashboard?
What should I see in the Collections section?
```

---

## DAY 3 — Hybrid Query Working

### Prompt 3-A
```
Explain to me in plain English what happens when I call hybrid_query():
1. What does "dense" search do? One sentence.
2. What does "sparse BM25" search do? One sentence.
3. What does "RRF fusion" do? One sentence.
4. What does "cross-encoder reranking" do? One sentence.
5. Why do we cap the cross-encoder at 15 documents on ARM CPU?

No code. Plain English only.
```

### Prompt 3-B
```
[drag src/core/retrieval.py into chat]

Check hybrid_query() for these specific issues:
1. Are dense AND sparse vectors both generated separately?
2. Is the Qdrant query_points using prefetch for both dense and sparse?
3. Is models.Fusion.RRF applied after prefetch?
4. Is the rerank_k parameter = 15 (cross-encoder input cap)?
5. Is tenant_filter applied in BOTH prefetch queries not just one?
6. Does it filter out results with score below 0.1?
7. Are ONNX thread settings at top of file?

List every issue.
```

### Prompt 3-C
```
Fix every issue. Show complete corrected src/core/retrieval.py.
Full file. No truncation.
```

### Prompt 3-D
```
Write complete scripts/test_retrieval.py:

1. Run hybrid_query("how does HNSW graph indexing work?", tenant_id="test")
2. Time each phase with time.perf_counter():
   Phase A: generate dense + sparse embeddings
   Phase B: Qdrant prefetch + RRF search
   Phase C: cross-encoder reranking
   Total end-to-end
3. Print top 5 results:
   [1] Score: 0.95 | "first 120 characters of chunk text..."
   [2] Score: 0.91 | "first 120 characters..."
   ... etc
4. Print timing:
   Phase A: Xms | Phase B: Xms | Phase C: Xms | Total: Xms
   Status: PASS (under 400ms) or SLOW (over 400ms)
5. Run same question dense-only search
   Print top 3 dense-only results
   Print: "Hybrid found X different chunks than dense-only"

All imports included. Run with: python3 scripts/test_retrieval.py
Full file.
```

### Prompt 3-E
```
I ran: python3 scripts/test_retrieval.py

Output:
[paste your actual output here]

1. Is the latency under 400ms total?
2. Are the chunks relevant to HNSW indexing?
3. Did hybrid find different chunks than dense-only?
4. If latency is over 400ms, which phase is slowest and how to speed it up?
```

---

## DAY 4 — /v1/query Endpoint Live

### Prompt 4-A
```
[drag src/api/main.py into chat]
[drag src/api/middleware/tenant.py into chat]

Check these two files together:
1. Is TenantMiddleware added to app BEFORE routes are registered?
2. Does TenantMiddleware skip health check endpoint /health?
3. Does it read rate limit from KeyDB (not hardcoded)?
4. Does it handle missing X-Tenant-ID header with 401?
5. Does it handle missing BYOK key gracefully (fall back to platform Groq key)?
6. Is Langfuse middleware also registered?
7. Does lifespan call warm_models() on startup?

List every issue.
```

### Prompt 4-B
```
Fix every issue. Show complete corrected src/api/main.py.
Full file. No truncation.
```

### Prompt 4-C
```
Show complete corrected src/api/middleware/tenant.py.
Full file. No truncation.
```

### Prompt 4-D
```
[drag src/api/routes/query.py into chat]
[drag src/core/generation.py into chat]

Check both files:
1. Does query.py call hybrid_query then pass results to generate_stream?
2. Is SSE format exactly: data: {"chunk": "text here"}\n\n ?
3. Is final SSE exactly: data: {"done": true}\n\n ?
4. Does generation.py use GROQ_API_KEY from os.environ?
5. Is the fallback chain: Groq → OpenRouter → Anthropic?
6. Does generate_stream yield chunks as they arrive (not wait for full response)?
7. Is fast_complete using groq/llama-3.1-8b-instant?

List every issue.
```

### Prompt 4-E
```
Fix every issue.

Show complete corrected src/api/routes/query.py. Full file.

[wait for response, then say "next"]
```

### Prompt 4-F
```
Show complete corrected src/core/generation.py. Full file. No truncation.
```

### Prompt 4-G
```
How do I:
1. Install all Python requirements on the server:
   pip install -r requirements.txt
   Are there any packages that need special handling on ARM?

2. Start the FastAPI server:
   uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
   What should I see in terminal output when it starts successfully?

3. Test with curl (show exact command):
   POST /v1/query
   Header: X-Tenant-ID: test
   Body: question = "what is HNSW indexing?", stream = true

4. What do the streaming chunks look like in the terminal?

5. Test non-streaming (show exact command):
   same question but stream = false
   Show expected JSON response format
```

### Prompt 4-H
```
I started the server and ran the curl.

Server output:
[paste terminal output]

Curl output:
[paste curl output]

Is it working correctly?
If there are errors, diagnose and show me the exact fix.
If it works, what should I check to confirm Phase 1 is fully complete?
```

---

## DAY 5 — Python SDK

### Prompt 5-A
```
[drag sdk/python/synapseos/client.py into chat]

Check AsyncSynapseClient for issues:
1. Does query() correctly set stream=False and return QueryResult?
2. Does query_stream() parse SSE lines correctly?
   Must strip "data: " prefix, parse JSON, yield chunk text
3. Does it handle the done:true payload to stop streaming?
4. Does ingest() return IngestJob with job_id field?
5. Does feedback() send rating as integer (+1 or -1)?
6. Are timeouts set: 60s for query, 120s for stream, 30s for ingest?
7. Does it raise on non-200 HTTP status?

List every issue.
```

### Prompt 5-B
```
Fix every issue. Show complete corrected sdk/python/synapseos/client.py.
Full file. No truncation.
```

### Prompt 5-C
```
Write complete scripts/test_sdk.py:

Assumes: pip install -e sdk/python/ already done
Assumes: API running at http://localhost:8000

import asyncio
from synapseos import AsyncSynapseClient

client = AsyncSynapseClient(
    base_url="http://localhost:8000",
    api_key="test-key",
    tenant_id="test"
)

Test 1 — query() non-streaming:
  result = await client.query("what is Qdrant?")
  Print answer text (first 200 chars)
  PASS if answer is not empty string

Test 2 — query_stream() streaming:
  Print "Streaming: " then each chunk on same line as it arrives
  Print newline when done
  PASS if at least 3 chunks received

Test 3 — ingest() queuing:
  job = await client.ingest(["https://python.org"])
  Print job.job_id
  PASS if job_id is not empty

Test 4 — feedback():
  await client.feedback("trace-test-123", rating=1)
  PASS if no exception raised

Print final: "X/4 tests passed"

Full file. All imports. Run with: python3 scripts/test_sdk.py
```

### Prompt 5-D
```
How do I install the SDK locally for testing?

Show:
1. pip install command
2. Verify it works: python3 -c "from synapseos import AsyncSynapseClient; print('OK')"
3. Run tests: python3 scripts/test_sdk.py
4. Expected output when all 4 tests pass
```

---

## DAY 6 — TypeScript SDK + SvelteKit Widget

### Prompt 6-A
```
[drag sdk/typescript/src/index.ts into chat]

Check SynapseOSClient TypeScript:
1. Does queryStream() correctly buffer SSE lines across chunk boundaries?
   (chunks may arrive split across multiple read() calls)
2. Does it strip "data: " prefix before JSON.parse?
3. Does it stop on payload.done === true?
4. Does query() non-streaming await full JSON response?
5. Are types complete: QueryResult, Source interfaces?
6. Does feedback() send { trace_id, rating } in body?
7. Are headers set correctly: Authorization and X-Tenant-ID?

List every issue.
```

### Prompt 6-B
```
Fix every issue. Show complete corrected sdk/typescript/src/index.ts.
Full file. No truncation.
```

### Prompt 6-C
```
Write a complete SvelteKit chat widget component.

File path: src/lib/components/RAGChatWidget.svelte

Requirements:
- Uses SynapseOSClient from '@synapseos/sdk'
- base_url from import.meta.env.VITE_SYNAPSE_URL
- api_key from import.meta.env.VITE_SYNAPSE_KEY
- tenant_id from import.meta.env.VITE_TENANT_ID
- Streaming: tokens appear character by character in real time
- Shows "Thinking..." with CSS animation while waiting
- Text input at bottom of chat
- Send button — also triggers on Enter key
- Auto-scrolls to bottom as tokens stream in
- Shows collapsed "Sources" section after each answer
- Thumbs up and thumbs down buttons on each assistant message
- Uses Tailwind CSS only (no custom CSS file)
- Dark theme compatible

Full Svelte component. All script/template/style in one file.
No truncation.
```

### Prompt 6-D
```
Write the SvelteKit server endpoint that proxies the SSE stream.

File path: src/routes/api/rag/+server.ts

It must:
- Accept POST with JSON body containing: question, session_id (optional)
- Read SYNAPSE_URL and SYNAPSE_KEY from $env/static/private (not exposed to browser)
- Read tenant_id from request header or default to "default"
- Forward request to SynapseOS /v1/query as SSE
- Pipe the SSE response back to the browser
- Set correct Content-Type: text/event-stream header
- Handle errors: return 500 with error message

Full TypeScript file. All SvelteKit imports correct.
```

### Prompt 6-E
```
Show me how to add RAGChatWidget to an existing SvelteKit page in 5 steps:
1. npm install command
2. .env variables to add (VITE_ prefix ones)
3. +page.svelte example showing how to import and use the widget
4. How to test it in browser
5. What a successful streaming response looks like in the browser
```

---

## DAY 7 — MCP Server

### Prompt 7-A
```
[drag mcp/synapse_mcp.py into chat]

Check synapse_mcp.py for FastMCP 2.2.9 issues:
1. Is FastMCP initialized correctly with name and instructions?
2. Do all @mcp.tool() decorators have complete docstrings?
   (The docstring is how the LLM decides when to use the tool)
3. Does query_knowledge return a plain string (not dict or object)?
4. Does think tool accept session_id parameter?
5. Does ingest_url return a string with the job_id?
6. Is transport="stdio" set in mcp.run()?
7. Does the client point to SYNAPSE_BASE_URL from environment?

List every issue.
```

### Prompt 7-B
```
Fix every issue and add these two new tools:

check_job_status(job_id: str) -> str
  Calls GET /v1/ingest/{job_id} on the SynapseOS API
  Returns: "Status: done | Chunks: 47" or "Status: processing" or "Status: failed"

get_stats() -> str
  Calls GET /v1/collections on SynapseOS API
  Returns formatted string:
  "Knowledge base: 12,450 vectors | Documents: 89 | Status: green"

Show complete corrected mcp/synapse_mcp.py. Full file. No truncation.
```

### Prompt 7-C
```
How do I install and run the MCP server?

1. pip install fastmcp — exact command
2. Environment variables to set before running
3. How to run: python3 mcp/synapse_mcp.py
4. What to see in terminal when it starts correctly
5. How to stop it
```

### Prompt 7-D
```
Show me the exact config file content for each IDE:

For Cursor — file: .cursor/mcp.json
(create this at project root)

For Claude Desktop/Code — file: claude_desktop_config.json
Mac location: ~/Library/Application Support/Claude/claude_desktop_config.json
Windows location: %APPDATA%\Claude\claude_desktop_config.json

For Windsurf — show exactly where to add MCP config in settings

Show each as complete JSON I copy exactly.
Replace paths with [ABSOLUTE_PATH_TO_REPO] placeholder.
```

### Prompt 7-E
```
How do I test the MCP integration is working?

1. After configuring Cursor, how do I verify it loaded the MCP server?
2. What do I type in Cursor chat to trigger query_knowledge?
3. What does a successful MCP tool call look like in Cursor?
4. If the MCP server fails to start, what are the 3 most common causes and fixes?
```

---

## DAY 8 — Cloudflare Workers Edge

### Prompt 8-A
```
[drag cloudflare/worker.ts into chat]
[drag cloudflare/wrangler.toml into chat]

Check both files:
1. Does SHA-256 hash include BOTH request body AND X-Tenant-ID header?
   (Without tenant ID in hash, tenant A could get tenant B's cached response)
2. Does it detect stream:true in body and bypass cache for streaming requests?
3. Is KV put() using expirationTtl from CACHE_TTL env var?
4. Is the wrangler.toml entry file pointing to worker.ts?
5. Is KV namespace binding named RAG_CACHE?
6. Are there TypeScript type errors?

List every issue.
```

### Prompt 8-B
```
Fix every issue.

Show complete corrected cloudflare/worker.ts. Full file. No truncation.
```

### Prompt 8-C
```
Show complete corrected cloudflare/wrangler.toml. Full file.
```

### Prompt 8-D
```
Give me exact step-by-step commands to deploy the Cloudflare Worker:

Step 1: Install wrangler globally
Step 2: Login to Cloudflare (what to do in browser)
Step 3: Create KV namespace — exact command — capture the namespace ID from output
Step 4: Update wrangler.toml — exactly which line to change with the namespace ID
Step 5: Set ORACLE_BACKEND secret — exact command — what value to use
Step 6: Deploy — exact command
Step 7: Get the deployed worker URL — where to find it
Step 8: Test it — exact curl command to verify it's working

All commands copy-paste ready.
```

### Prompt 8-E
```
The worker is deployed. Show me:

1. Curl command for first request (should get MISS):
   Include headers that show cache status

2. Identical curl command for second request (should get HIT in under 50ms):
   Show expected response headers difference

3. How to check cache hit rate in Cloudflare dashboard

4. How to clear the KV cache completely if needed:
   Show wrangler kv command

5. How to verify my Oracle ARM is no longer being called on cache hits
```

---

## DAY 9 — Memory (mem0)

### Prompt 9-A
```
[drag src/cognitive/memory.py into chat]

Check memory.py:
1. Is mem0 LLM config using Groq (groq provider, llama-3.1-8b-instant model)?
2. Is Qdrant collection set to "synapse_memory" (not synapse_knowledge)?
3. Is embedder using fastembed BAAI/bge-base-en-v1.5?
4. Is history_db_path pointing to PostgreSQL (DATABASE_URL env var)?
5. Does load_session() correctly read alternating role/content from KeyDB list?
6. Does append_session() set expiry to 86400 seconds (24 hours)?
7. Is write_memory() wrapped in try/except so it never crashes the response?
8. Does load_memories() return empty string (not None) when no memories found?

List every issue.
```

### Prompt 9-B
```
Fix every issue. Show complete corrected src/cognitive/memory.py.
Full file. No truncation.

Also: is there any known issue installing mem0ai on Oracle ARM Ubuntu 22.04?
If yes, show the exact pip install command that works.
```

### Prompt 9-C
```
Write complete scripts/test_memory.py:

This proves memory persists ACROSS separate session IDs.

Step 1 — Store a memory:
  user_id = "rahul", tenant_id = "test"
  messages = [
    {"role": "user", "content": "My name is Rahul. I run a digital marketing agency in Bangladesh called SR Creative Hub."},
    {"role": "assistant", "content": "Got it! I'll remember that you're Rahul, running SR Creative Hub in Bangladesh."}
  ]
  Call write_memory("rahul", "test", messages)
  Print "Memory written. Facts stored by mem0."
  await asyncio.sleep(2)

Step 2 — Recall in different session:
  session_id = "totally-new-session-xyz"
  question = "What is my name and what business do I run?"
  memories = await load_memories("rahul", "test", question)
  Print "Memories recalled:"
  Print memories
  Print "PASS: memory recalled across sessions" if "Rahul" in memories else "FAIL: no memory"

Step 3 — Verify in Qdrant:
  Connect to Qdrant, query synapse_memory collection
  Print "Vectors in synapse_memory: X"

Run with: python3 scripts/test_memory.py
Full file. All imports. Use asyncio.run() for main.
```

### Prompt 9-D
```
[drag src/api/routes/think.py into chat]

Update think.py to wire in memory:
1. Request body must include: question, session_id, user_id
2. At start: load_session() and load_memories() with asyncio.gather() in parallel
3. Pass session context and long-term memory into generation
4. At end: write_memory() as asyncio.create_task() — never await it
5. Include memories_recalled count in response

Show complete updated src/api/routes/think.py. Full file. No truncation.
```

---

## DAY 10 — Self-Reflection

### Prompt 10-A
```
[drag src/cognitive/reflection.py into chat]

Check reflect_and_refine():
1. Does it use groq/llama-3.1-8b-instant as judge model? (fast, cheap)
2. Does the reflection prompt ask for JSON output with exact keys:
   relevancy, faithfulness, completeness, critique?
3. Is JSON parsing in try/except — returns original answer if parse fails?
4. Is combined score: 0.4*faithfulness + 0.3*relevancy + 0.3*completeness?
5. Is max_retries=1 enforced — hard stop after one retry?
6. Does it return (answer, {}) if reflection itself throws an exception?
7. Does it truncate context to 1500 chars for the judge prompt? (speed)

List every issue.
```

### Prompt 10-B
```
Fix every issue. Show complete corrected src/cognitive/reflection.py.
Full file. No truncation.
```

### Prompt 10-C
```
Write complete scripts/test_reflection.py:

context = "SynapseOS uses Qdrant for vector storage. It uses Groq for LLM routing. It runs on Oracle ARM."

Test Case A — Great answer:
  question = "What does SynapseOS use for vector storage?"
  answer = "SynapseOS uses Qdrant for vector storage."
  Run reflect_and_refine(question, context, answer)
  Print: faithfulness, relevancy, completeness, combined score
  Print: "Retry triggered: Yes/No"
  PASS if combined >= 0.70 and retry = No

Test Case B — Vague answer:
  question = "What does SynapseOS use?"
  answer = "SynapseOS uses various advanced technologies."
  Run reflect_and_refine(question, context, answer)
  Print: original scores, retry triggered, improved answer
  PASS if retry = Yes and improved answer is more specific

Test Case C — Hallucinated answer:
  question = "What LLM does SynapseOS use?"
  answer = "SynapseOS uses OpenAI GPT-4 and Pinecone for storage."
  Run reflect_and_refine(question, context, answer)
  Print: faithfulness score (should be low), retry triggered, corrected answer
  PASS if faithfulness < 0.5 and retry = Yes

Print: "X/3 cases behaved correctly"
Full file. asyncio.run(main()) pattern.
```

### Prompt 10-D
```
[drag src/api/routes/query.py into chat]

Update query.py to add reflection after generation:
1. After generate() or generate_stream() gets an answer, call reflect_and_refine()
2. For streaming: collect full answer from stream, then reflect, then return reflected answer
3. Add reflection_scores to response JSON for non-streaming
4. Add "retried": true/false to response JSON
5. If reflection raises exception, return original answer (never fail the request)

Show complete updated src/api/routes/query.py. Full file. No truncation.
```

### Prompt 10-E
```
Test the updated /v1/query endpoint with reflection.

Show me exact curl command to:
1. POST /v1/query with stream=false
2. Response should now include reflection_scores and retried fields

Show expected response JSON format with the new fields.

Then: how do I verify in Langfuse at port 3100 that reflection is being traced?
```

---

## DAY 11 — Tool Executor

### Prompt 11-A
```
[drag src/cognitive/tools.py into chat]

Check ToolExecutor for each built-in tool:

retrieve_knowledge:
- Does it call hybrid_query from src.core.retrieval?
- Does it pass tenant_id correctly?
- Does it join chunks with double newline?

web_search:
- Does Crawl4AI have page_timeout=15000?
- Does it cap output at 3000 characters?
- Does it use a real search URL (not just fetch a page)?

calculate:
- Does it check every character against allowed set before eval?
- Allowed set: 0-9 + - * / ( ) . , space — NOTHING ELSE
- Does it return "Error: unsafe expression" for anything else?

call_api:
- Is Fernet used to decrypt auth_header from database?
- Is httpx timeout set to 15 seconds?
- Is output capped at 3000 chars?

List every issue in each tool.
```

### Prompt 11-B
```
Fix every issue. Show complete corrected src/cognitive/tools.py.
Full file. No truncation.
```

### Prompt 11-C
```
[drag src/core/generation.py into chat]

Add a new function to generation.py:

async def generate_with_tools(
    question: str,
    context: str,
    available_tools: list[dict],
    tenant_api_key: str = None
) -> tuple[str, list[str]]:

It must:
1. Build messages with system prompt + context + question
2. Call LiteLLM with tools parameter (OpenAI function calling format)
3. If response has tool_calls: execute ALL of them in parallel with asyncio.gather
4. Build ToolExecutor and call execute() for each tool call
5. Append tool results to messages
6. Call LiteLLM again to get final answer using tool results
7. Return (final_answer_text, list_of_tool_names_used)

Use groq/llama-3.1-70b-versatile (Groq supports function calling).
Show complete updated src/core/generation.py. Full file. No truncation.
```

### Prompt 11-D
```
Write complete scripts/test_tools.py:

from src.cognitive.tools import ToolExecutor
import asyncio

executor = ToolExecutor()

Test 1 — web_search:
  result = await executor.execute("web_search", {"query": "Qdrant vector database python"}, "test")
  Print result (first 300 chars)
  PASS if result is not empty

Test 2 — calculate (valid):
  result = await executor.execute("calculate", {"expression": "(42 * 1.5) + 10"}, "test")
  Print result
  PASS if result == "73.0"

Test 3 — calculate (injection attempt):
  result = await executor.execute("calculate", {"expression": "__import__('os').system('ls')"}, "test")
  Print result
  PASS if "Error" in result

Test 4 — retrieve_knowledge:
  result = await executor.execute("retrieve_knowledge", {"query": "HNSW graph indexing"}, "test")
  Print result (first 200 chars)
  PASS if result is not empty

Print: "X/4 tool tests passed"
Full file. asyncio.run(main()) pattern.
```

---

## DAY 12 — /v1/think Full Cognitive Engine

### Prompt 12-A
```
[drag src/cognitive/engine.py into chat]

Check cognitive_query() step by step:

Step 1 Memory Load:
- Are load_session() and load_memories() called with asyncio.gather()?
- (They must run in parallel, not sequential)

Step 2 Classify:
- Is classify_query() calling fast_complete() with groq 8b?
- Does it default to "simple" if classification fails?

Step 3 Execute:
- Simple path: calls hybrid_query then generate?
- Complex path: calls hybrid_query with session + memory context?
- Tool path: calls generate_with_tools with BUILTIN_SCHEMAS?

Step 4 Reflect:
- Is reflect_and_refine() called on the final answer?

Step 5 Memory Write:
- Is write_memory() called with asyncio.create_task()?
  (Must be create_task not await — never block the response)
- Is append_session() also create_task?

List every issue.
```

### Prompt 12-B
```
Fix every issue. Show complete corrected src/cognitive/engine.py.
Full file. No truncation.
```

### Prompt 12-C
```
[drag src/api/routes/think.py into chat]

Check think.py:
1. Does request body include: question, session_id, user_id?
2. Does it call cognitive_query() with all three?
3. Does response include ALL fields:
   answer, query_type, steps_taken, reflection_scores, memories_recalled, tools_used?
4. Does it support both streaming and non-streaming?

Fix any issues. Show complete corrected src/api/routes/think.py. Full file.
```

### Prompt 12-D
```
Write complete scripts/test_think.py:

Assumes: API running at http://localhost:8000
Uses httpx to make real HTTP calls.

import httpx, asyncio

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "test", "Content-Type": "application/json"}

Test A — Simple retrieval:
  POST /v1/think
  body: question="what is HNSW indexing?", session_id="think-A", user_id="rahul"
  Print: query_type (expect "simple"), answer (first 200 chars)
  PASS if query_type == "simple"

Test B — Memory recall:
  POST /v1/think
  body: question="what is my name?", session_id="think-B", user_id="rahul"
  (Rahul's name stored in mem0 from Day 9 test)
  Print: memories_recalled count, answer
  PASS if memories_recalled > 0 and "Rahul" in answer

Test C — Tool use:
  POST /v1/think
  body: question="search the web for Qdrant 2025 new features", session_id="think-C", user_id="rahul"
  Print: query_type (expect "tool"), tools_used, answer (first 200 chars)
  PASS if "web_search" in tools_used

Print final: "X/3 cognitive tests passed"
Full file. asyncio.run(main()) pattern.
```

### Prompt 12-E
```
I ran: python3 scripts/test_think.py

Output:
[paste your actual output here]

1. How many tests passed?
2. If any failed, what is the most likely cause?
3. Show me the exact curl command for a complete demo test of /v1/think
4. What should I check in Langfuse at port 3100 to verify all 3 cognitive paths are being traced?
```

### Prompt 12-F
```
SynapseOS Phase 3 is complete. Give me:

1. Git commands to commit everything:
   git add -A
   git commit -m "phase 3 complete: cognitive engine with memory, tools, reflection"
   git push origin main

2. Final verification checklist I run top to bottom:
   [ ] All Docker services up: docker compose ps
   [ ] Ingest works: python3 scripts/test_ingest.py
   [ ] Query works: python3 scripts/test_retrieval.py
   [ ] Endpoint works: curl /v1/query streaming
   [ ] Python SDK: python3 scripts/test_sdk.py
   [ ] Cognitive: python3 scripts/test_think.py
   [ ] Langfuse: open port 3100, check traces
   [ ] Cloudflare: second request shows X-Cache: HIT

3. What is the one curl command I can show anyone to demo SynapseOS?
```

---

## EMERGENCY PROMPTS

### When you get a Python error
```
I got this error running [command]:

[paste complete error traceback — all lines]

The file that caused it:
[drag the file]

Find the exact bug and show me the complete corrected file.
Full file. No truncation.
```

### When a Docker service won't start
```
The [service name] container keeps failing.

Logs:
[docker compose logs servicename — last 30 lines]

My docker-compose.yml service section for it:
[paste just that service block]

What is wrong and how do I fix it?
Show exact changes to make.
```

### When output cuts off mid-file
```
continue
```

### When GLM forgets the stack
```
Remember: Oracle ARM 4 vCPU 24GB NO GPU. Qdrant + fastembed + Groq + mem0 + KeyDB + MinIO.
OMP_NUM_THREADS=4. batch_size 64/16. cross-encoder max 15 docs. KeyDB AOF no RDB.
Give complete files. No truncation.
```

### When you need a specific file explained
```
[drag the file]

Explain what this file does in plain English.
Then tell me: is there anything in it that could cause problems on Oracle ARM?
```
