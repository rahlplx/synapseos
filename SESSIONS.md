# SynapseOS — Daily Session Guide

> Build SynapseOS step by step using chat.z.ai web app.
> One session per day. One focused goal per session. Copy → paste → ship.

---

## How to Use chat.z.ai Web App

### Setup (do once)
1. Go to **chat.z.ai** → sign in
2. Get your API key → z.ai/manage-apikey/apikey-list (add to `.env` as `ZAI_API_KEY`)
3. Bookmark chat.z.ai — this is your daily IDE

### Every Session — The Ritual
```
1. Open chat.z.ai → click "New Chat" (fresh context every session)
2. Copy the SESSION STARTER BLOCK below
3. Paste it → hit Enter
4. Wait for GLM-5.1 to confirm it understood
5. Then paste TODAY'S SESSION PROMPT
6. Work through the output — copy code → paste into repo files
7. Test the feature
8. Paste the SESSION CLOSER prompt
9. Copy the session log output → paste into AGENTS.md at the bottom
```

### chat.z.ai Tips
- **200K context** — paste entire files, it won't break
- **New chat = new session** — never continue yesterday's chat
- **If output cuts off** — type "continue" and it resumes
- **For long files** — say "show me the complete file, no truncation"
- **Code blocks** — always ask for complete files, not diffs
- **If it hallucinates** — paste the actual current file and say "fix this specific file"
- **File uploads** — drag .py, .yaml files directly into chat
- **Web search** — it can search docs in real time (just ask)

---

## SESSION STARTER BLOCK
> Copy-paste this at the START of every new chat session

```
You are GLM-5.1 building SynapseOS — a self-improving BYOK RAG platform.

LOCKED STACK (never suggest alternatives):
- FastAPI + Uvicorn | Qdrant 1.13.5 | fastembed BAAI/bge-base-en-v1.5 768d
- LiteLLM → z.ai GLM-5.1 primary (api_base: https://api.z.ai/api/paas/v4/)
- KeyDB (Redis-compatible) | MinIO | PostgreSQL | Crawl4AI | Docling
- mem0ai (Qdrant + PG backend) | RAGAS 0.2.15 | DSPy 2.5.20
- Langfuse v3 self-hosted | FastMCP 2.2.9 | Cloudflare Workers
- Deploy: Coolify on Oracle ARM (4 vCPU / 24GB RAM, NO GPU)

CRITICAL RULES:
- OMP_NUM_THREADS=4 always for ONNX on ARM
- Qdrant batch_size=64 ingest, 16 query
- Cross-encoder input cap = 15 docs max
- KeyDB: AOF only, NO RDB (fork causes OOM on ARM)
- Docling concurrency = 1 always
- All LLM calls use: model="openai/glm-5.1", api_base="https://api.z.ai/api/paas/v4/"
- Tenant isolation via payload filter (tenant_id field), NOT separate collections
- mem0 collection = "synapse_memory", knowledge = "synapse_knowledge"
- Never hardcode API keys — always os.environ["KEY_NAME"]

REPO: github.com/rahlplx/synapseos
I am a non-technical founder (vibe coder). Give me complete, production-ready files I can copy directly into the repo. No partial snippets. Always show the full file.

Confirm you understand the stack and rules. Then I will give you today's task.
```

---

## SESSION CLOSER
> Copy-paste this at the END of every session

```
Session complete. Give me:

1. A 3-line summary of what was built today
2. The exact files that were created or modified (list only)
3. The test command to verify this works
4. What to build in the next session
5. Any blockers or ARM-specific issues to watch

Format as a session log entry I can paste into AGENTS.md.
```

---

## Phase 1 — Core RAG Engine (Sessions 1–4)

---

### SESSION 1 — Docker Compose + All Services Live

**Goal**: Every service starts healthy. Zero errors in logs.

```
Today's task: SESSION 1 — Docker Compose Setup

I have this docker-compose.yml in my repo: [paste contents of docker-compose.yml]
I have this .env.example: [paste contents of .env.example]

Do this:
1. Review my docker-compose.yml for any ARM-specific issues or missing configs
2. Show me the exact .env file I need to create (with placeholder values I need to fill)
3. Show me the exact commands to run in order:
   - Fill .env
   - Start services
   - Verify each service is healthy
4. Show me how to check logs for each service if something fails
5. Show me the expected output of ./scripts/healthcheck.sh when everything is working

Give me a step-by-step checklist I can follow without knowing Docker deeply.
After running this, I should have: Qdrant ✅ PostgreSQL ✅ KeyDB ✅ MinIO ✅ LiteLLM ✅ Langfuse ✅
```

---

### SESSION 2 — Qdrant Collection + First Ingest

**Goal**: Scrape one URL, chunk it, embed it, store in Qdrant. Verify vectors exist.

```
Today's task: SESSION 2 — Qdrant Collection + First URL Ingest

Current state: All Docker services are running from Session 1.

My current ingestion code is in src/core/ingestion.py: [paste file]
My current retrieval.py has ensure_collection(): [paste file]

Do this:
1. Review ingestion.py for ARM issues (ONNX threads, batch sizes, Docling concurrency)
2. Show me how to run the collection creation (ensure_collection) as a one-time setup script
3. Write a standalone test script tests/test_ingest.py that:
   - Creates the Qdrant collection
   - Ingests this URL: https://docs.z.ai/guides/overview/quick-start
   - Verifies vectors were stored (query Qdrant for count)
   - Prints: chunks ingested, time taken, RAM used
4. Show me how to run it: python tests/test_ingest.py
5. Show me how to verify in Qdrant dashboard (port 6333) that vectors exist

Give me the complete test file and all commands.
```

---

### SESSION 3 — Hybrid Query Working

**Goal**: Given a question, retrieve top 5 chunks. Verify reranker works.

```
Today's task: SESSION 3 — Hybrid RAG Query Working

Current state: Vectors are in Qdrant from Session 2.

My retrieval.py: [paste file]

Do this:
1. Review hybrid_query() for correctness — especially:
   - Dense + sparse vectors both being generated
   - RRF fusion via Qdrant Query API
   - Cross-encoder reranking (cap at 15 docs input)
   - tenant_id filter applied correctly
2. Write tests/test_retrieval.py that:
   - Runs hybrid_query("what is GLM-5.1?", tenant_id="test")
   - Prints: top 5 chunks with scores
   - Prints: latency breakdown (embed/search/rerank separately)
   - Prints: P95 target vs actual (target: <235ms without HyDE)
3. Fix any issues you find in retrieval.py — show me the complete fixed file
4. Show me the run command

The output should prove hybrid beats dense-only on keyword queries.
```

---

### SESSION 4 — /v1/query Endpoint Live with z.ai Streaming

**Goal**: POST /v1/query returns a streaming answer from GLM-5.1.

```
Today's task: SESSION 4 — /v1/query Endpoint Live

Current state: hybrid_query() works from Session 3.

My current files:
- src/api/main.py: [paste]
- src/api/routes/query.py: [paste]
- src/api/middleware/tenant.py: [paste]
- src/core/generation.py: [paste]

Do this:
1. Review all 4 files for issues with:
   - z.ai GLM-5.1 integration (model="openai/glm-5.1", api_base correct)
   - SSE streaming format (data: {chunk}\n\n)
   - TenantMiddleware correctly injecting tenant_id before routes fire
   - BYOK key passthrough to LiteLLM
2. Fix any issues — show me complete corrected files
3. Write tests/test_query_endpoint.py using httpx that:
   - Starts the FastAPI app via TestClient
   - POSTs to /v1/query with X-Tenant-ID: test header
   - Verifies it gets a streaming response
   - Prints the full answer
4. Show me the curl command to test manually:
   curl -X POST http://localhost:8000/v1/query \
     -H "X-Tenant-ID: test" \
     -H "Content-Type: application/json" \
     -d '{"question": "what is SynapseOS?", "stream": true}'
5. Show me how to start the server: uvicorn src.api.main:app --reload

Phase 1 complete when this curl returns a streaming GLM-5.1 answer.
```

---

## Phase 2 — SDK + MCP (Sessions 5–8)

---

### SESSION 5 — Python SDK Tested End-to-End

```
Today's task: SESSION 5 — Python SDK Working

Current state: /v1/query endpoint is live from Session 4.

My SDK: sdk/python/synapseos/client.py: [paste]

Do this:
1. Review AsyncSynapseClient for correctness
2. Write tests/test_sdk.py that tests all methods:
   - client.query() — non-streaming
   - client.query_stream() — streaming, print chunks as they arrive
   - client.ingest() — queue a URL, poll for completion
   - client.feedback() — submit +1 rating
3. Fix any issues in client.py — show complete file
4. Show me how to install and test the SDK locally:
   pip install -e sdk/python/
   python tests/test_sdk.py
```

---

### SESSION 6 — TypeScript SDK + SvelteKit Widget

```
Today's task: SESSION 6 — TypeScript SDK + SvelteKit Chat Widget

My TS SDK: sdk/typescript/src/index.ts: [paste]

Do this:
1. Review SynapseOSClient TypeScript for correctness
2. Show me a complete SvelteKit chat widget (ChatWidget.svelte) that:
   - Uses SynapseOSClient.queryStream()
   - Shows streaming tokens as they arrive (letter by letter)
   - Has a text input + send button
   - Shows sources after answer
   - Has thumbs up/down feedback buttons
   - Works with shadcn-svelte components
3. Show me how to drop this into an existing SvelteKit app
4. Fix any TS SDK issues — show complete corrected file
```

---

### SESSION 7 — FastMCP Server + Claude Code Integration

```
Today's task: SESSION 7 — MCP Server Live

My MCP server: mcp/synapse_mcp.py: [paste]

Do this:
1. Review synapse_mcp.py for FastMCP 2.2.9 compatibility
2. Show me how to install and run it:
   pip install fastmcp
   python mcp/synapse_mcp.py
3. Show me the exact .cursor/mcp.json config to add SynapseOS to Cursor
4. Show me the exact claude_desktop_config.json to add to Claude Code
5. Show me the exact config for Windsurf / Cline
6. Write a test: ask Claude Code "query knowledge: what is hybrid retrieval?"
   and show me what the expected MCP response looks like
7. Add a new tool to synapse_mcp.py: get_collection_stats()
   Show complete updated file
```

---

### SESSION 8 — Cloudflare Workers Edge Deployed

```
Today's task: SESSION 8 — Cloudflare Workers Edge Cache Live

My worker: cloudflare/worker.ts: [paste]

Do this:
1. Review worker.ts for correctness — especially:
   - SHA-256 hash includes X-Tenant-ID (prevents cross-tenant cache pollution)
   - Streaming responses are NOT cached (stream:true bypass)
   - KV TTL set correctly
2. Show me exact wrangler.toml config for this worker
3. Show me the step-by-step deployment:
   npm install -g wrangler
   wrangler login
   wrangler kv:namespace create RAG_CACHE
   wrangler deploy cloudflare/worker.ts
4. Show me how to verify a cache HIT vs MISS:
   - First request: X-Cache: MISS
   - Same request again: X-Cache: HIT, latency <50ms
5. Show me how to set ORACLE_BACKEND env var in Cloudflare dashboard
```

---

## Phase 3 — Cognitive Engine (Sessions 9–12)

---

### SESSION 9 — mem0 Memory Working

```
Today's task: SESSION 9 — Conversation Memory with mem0

Current state: /v1/query is live. Now adding memory to /v1/think.

My cognitive memory module: src/cognitive/memory.py: [paste]

Do this:
1. Install mem0: pip install mem0ai
2. Review memory.py for:
   - mem0 config pointing to our Qdrant (synapse_memory collection)
   - GLM-5.1 as the mem0 LLM judge (OpenAI-compatible config)
   - fastembed as embedder (BAAI/bge-base-en-v1.5)
   - session cache in KeyDB (sliding window 10 turns)
3. Fix any issues — show complete corrected memory.py
4. Write tests/test_memory.py that:
   - Turn 1: "My name is Rahul and I run a digital marketing agency"
   - Turn 2: "What do I do for work?"
   - Verify Turn 2 answer uses memory from Turn 1 WITHOUT being in the same context window
   - Print: memories extracted, memories recalled, answer
5. Show me how mem0 stores facts in Qdrant (what the synapse_memory collection looks like)
```

---

### SESSION 10 — Self-Reflection Working

```
Today's task: SESSION 10 — Self-Reflection (GLM-5.1 judges its own answers)

My reflection module: src/cognitive/reflection.py: [paste]

Do this:
1. Review reflect_and_refine() for:
   - GLM-5.1 as the judge (not a different model)
   - JSON output parsing robustness
   - Score threshold logic (combined ≥ 0.7 → return, else retry once)
   - Max 1 retry to prevent infinite loops
2. Fix any issues — show complete corrected reflection.py
3. Write tests/test_reflection.py that tests 3 cases:
   Case A: Good answer (score ≥ 0.7) → returned as-is
   Case B: Bad answer (score < 0.7) → retried and improved
   Case C: Hallucinated answer (not in context) → rejected and corrected
   Print scores for each case and whether retry was triggered
4. Add reflection automatically to /v1/query route — update routes/query.py
   Show complete updated file
```

---

### SESSION 11 — Tool Executor Working

```
Today's task: SESSION 11 — Tool Use (web search + API calls)

My tools module: src/cognitive/tools.py: [paste]

Do this:
1. Review ToolExecutor for all 4 built-in tools:
   - retrieve_knowledge: calls hybrid_query
   - web_search: uses Crawl4AI to fetch Brave search results
   - calculate: safe eval (numbers + operators only)
   - call_api: tenant custom HTTP tool (load from DB, decrypt auth header)
2. Fix any issues — show complete corrected tools.py
3. Wire LiteLLM function calling — update src/core/generation.py to add:
   async def generate_with_tools(question, context, tools, tenant_api_key)
   This should: call GLM-5.1 with tool schemas → execute tool calls → final answer
   Show complete updated generation.py
4. Write tests/test_tools.py:
   - Test web_search("latest Qdrant version") → returns real web result
   - Test calculate("(42 * 1.5) + 10") → returns 73.0
   - Test retrieve_knowledge("what is hybrid retrieval") → returns chunks
```

---

### SESSION 12 — /v1/think Endpoint Complete

```
Today's task: SESSION 12 — Full Cognitive Engine (/v1/think)

This is the final session. Wire everything together.

My files:
- src/cognitive/engine.py: [paste]
- src/api/routes/think.py: [paste]

Do this:
1. Review cognitive_query() orchestrator:
   - Step 1: Load session (KeyDB) + long-term memory (mem0) in parallel
   - Step 2: Classify query (simple/complex/tool) using GLM-5.1
   - Step 3: Route to correct handler
   - Step 4: Self-reflect on answer
   - Step 5: Write memory (fire-and-forget, non-blocking)
2. Fix any issues — show complete corrected engine.py
3. Show complete corrected think.py route
4. Write tests/test_think.py — end-to-end test:
   Session: "I am building a RAG platform for marketing agencies"
   Query 1: "What am I building?" → should use memory
   Query 2: "Search the web for best RAG frameworks 2025" → should use web_search tool
   Query 3: "What is 42% of our £50k budget?" → should use calculate tool
   Print: query_type, steps_taken, reflection_scores, memories_recalled, tools_used
5. Final curl test — show me the complete /v1/think curl command

SynapseOS Phase 3 complete when all 3 query types work end-to-end.
```

---

## Quick Reference

### Daily File Operations in chat.z.ai

**To paste a file into chat:**
```
Here is my current [filename]:

```python
[paste entire file contents]
```

Review it and fix any issues for ARM deployment.
```

**To get a complete fixed file back:**
```
Show me the complete corrected [filename] — full file, no truncation, no "..." shortcuts.
```

**If GLM-5.1 output is cut off:**
```
continue
```

**If it forgets the stack:**
```
Remember: locked stack is FastAPI + Qdrant + fastembed + z.ai GLM-5.1 + LiteLLM + KeyDB + MinIO + Coolify on Oracle ARM (4 vCPU / 24GB, no GPU). Never suggest alternatives.
```

**To debug an error:**
```
I got this error when running [command]:

[paste full error traceback]

My current [relevant file]: [paste file]

Fix it. Show me the complete corrected file.
```

### Session Log Template (paste into AGENTS.md)

```markdown
## Session YYYY-MM-DD — [What was built]
- Built: [list features]
- Files modified: [list files]
- Test command: [command]
- Status: ✅ working / ⚠️ partial / ❌ blocked
- Next session: [what to build]
- Blockers: [any issues]
```
