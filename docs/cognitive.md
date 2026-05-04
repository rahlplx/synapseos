# SynapseOS — Cognitive Engine (Layer 7)

> Sits on top of the 6-layer RAG core. Makes SynapseOS think, not just retrieve.
> Version: 1.0.0 | All components CPU-only, ARM-safe, zero paid dependencies.

---

## What Changes at Layer 7

| Without Cognitive Engine | With Cognitive Engine |
|---|---|
| One-shot: query → retrieve → generate | Multi-step: plan → reason → act → reflect |
| Stateless (no memory between sessions) | Stateful (remembers users, facts, context) |
| Retrieval only | Retrieval + tool calls + web search + API calls |
| Returns first answer | Evaluates own answer, retries if insufficient |
| Gets smarter nightly (DSPy batch) | Gets smarter per query (inline reflection) |

---

## OSS Stack for Cognitive Layer

| Capability | Package | Version | Why |
|---|---|---|---|
| Long-term memory | mem0ai | 0.1.100+ | Self-hosted, Qdrant + PostgreSQL backend — our locked stack |
| Session memory | KeyDB | existing | Sliding window last 10 turns per session |
| Multi-step reasoning | DSPy ReAct | 2.5.20+ | Already in stack. ReAct = Reason + Act in loops |
| Tool use | LiteLLM function calling | existing | Native tool/function schema support |
| Tool registry | PostgreSQL | existing | Tenant-defined tools stored + versioned |
| Tool executor | httpx async | existing | Executes any HTTP tool call |
| Built-in web search | Crawl4AI | existing | Tool: `web_search` |
| Self-reflection | Groq Llama-3.1-8b | existing via LiteLLM | Fast inline judge — ~200ms on Groq |
| Query classifier | Groq Llama-3.1-8b | existing | Classifies: simple / complex / tool-needed |

**mem0 is the key addition.** It automatically extracts facts from conversations, stores them in Qdrant (`synapse_memory` collection), and recalls them on future sessions — using infrastructure you already run.

---

## Cognitive Engine Architecture

```
User Query + Session ID + Tenant ID
              │
              ▼
┌─────────────────────────────────────────────────────┐
│  STEP 1 — MEMORY LOAD                               │
│  KeyDB: load last 10 turns (session context)        │
│  mem0: recall relevant long-term memories           │
│  Output: enriched context for this query            │
└─────────────────────┬───────────────────────────────┘
                      │
              ▼
┌─────────────────────────────────────────────────────┐
│  STEP 2 — QUERY CLASSIFICATION (fast LLM, ~100ms)  │
│  simple   → one-shot RAG (existing L2+L3)          │
│  complex  → multi-step planner                      │
│  tool     → tool execution + RAG synthesis          │
└─────────────────────┬───────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────┐         ┌─────────────────────────┐
│ SIMPLE PATH   │         │ COMPLEX / TOOL PATH      │
│ L2 Retrieval  │         │ DSPy ReAct Planner       │
│ L3 Generation │         │  → Thought: what needed? │
│ ↓             │         │  → Act: retrieve / call  │
│ Self-Reflect  │         │  → Observe: got result   │
│ ↓             │         │  → Repeat until done     │
│ Return        │         │  → Synthesize            │
└───────┬───────┘         │  → Self-Reflect          │
        │                 └────────────┬────────────┘
        │                              │
        └──────────────┬───────────────┘
                       │
              ▼
┌─────────────────────────────────────────────────────┐
│  STEP 3 — SELF-REFLECTION                           │
│  Fast judge LLM checks:                             │
│  - Does answer address the question? (relevancy)    │
│  - Is answer grounded in context? (faithfulness)    │
│  - Is answer complete? (no obvious gaps)            │
│  Score ≥ 0.7 → return answer                        │
│  Score < 0.7 → inject critique → regenerate (1×)   │
│  Max 2 reflection cycles (prevent infinite loop)    │
└─────────────────────┬───────────────────────────────┘
                      │
              ▼
┌─────────────────────────────────────────────────────┐
│  STEP 4 — MEMORY WRITE                              │
│  mem0: extract important facts from this exchange   │
│  Store: user preferences, key decisions, entities  │
│  KeyDB: append turn to session window              │
└─────────────────────────────────────────────────────┘
              │
              ▼
         Streaming Response
```

---

## Component 1 — Conversation + Long-Term Memory (mem0)

mem0 automatically extracts facts from conversations and recalls them later. No manual memory management.

### mem0 Config (uses your existing Qdrant + PostgreSQL)

```python
# synapseos/cognitive/memory.py
from mem0 import Memory

config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "qdrant",
            "port": 6333,
            "collection_name": "synapse_memory",   # separate from knowledge collection
            "embedding_model_dims": 768,
        }
    },
    "llm": {
        "provider": "litellm",
        "config": {
            "model": "groq/llama-3.1-8b-instant",
            "api_key": "os.environ/GROQ_API_KEY",
        }
    },
    "embedder": {
        "provider": "fastembed",
        "config": {
            "model": "BAAI/bge-base-en-v1.5",
        }
    },
    "history_db_path": "postgresql://synapse:pass@postgres:5432/synapseos",
}

memory = Memory.from_config(config)
```

### Memory Operations

```python
async def load_memories(user_id: str, tenant_id: str, query: str) -> str:
    """Recall relevant long-term memories for this query."""
    results = memory.search(
        query=query,
        user_id=f"{tenant_id}:{user_id}",
        limit=5,
    )
    if not results["results"]:
        return ""
    facts = [r["memory"] for r in results["results"]]
    return "Relevant memory:\n" + "\n".join(f"- {f}" for f in facts)


async def write_memory(
    user_id: str,
    tenant_id: str,
    messages: list[dict],
):
    """Extract and store important facts from this conversation turn."""
    memory.add(
        messages=messages,
        user_id=f"{tenant_id}:{user_id}",
        metadata={"tenant_id": tenant_id},
    )


async def load_session(session_id: str, window: int = 10) -> list[dict]:
    """Load last N turns from KeyDB session cache."""
    raw = await keydb.lrange(f"session:{session_id}", -window * 2, -1)
    turns = []
    for i in range(0, len(raw), 2):
        turns.append({
            "role": raw[i].decode(),
            "content": raw[i+1].decode(),
        })
    return turns


async def append_session(session_id: str, role: str, content: str):
    """Append turn to session window. Auto-expires after 24h."""
    await keydb.rpush(f"session:{session_id}", role, content)
    await keydb.expire(f"session:{session_id}", 86400)
```

**What mem0 auto-extracts from conversations:**
- User preferences ("I prefer concise answers")
- Entity facts ("Our client budget is £50k")
- Decisions made ("We agreed to use FastAPI")
- Context that matters later ("This is for the Q4 campaign")

---

## Component 2 — Multi-Step Reasoning (DSPy ReAct)

DSPy ReAct loops: Thought → Action → Observation → repeat until done.

```python
# synapseos/cognitive/planner.py
import dspy
from synapseos.core.retrieval import hybrid_query
from synapseos.cognitive.tools import ToolExecutor

class SynapseReAct(dspy.Module):
    """
    ReAct agent for complex multi-step queries.
    Tools available: retrieve_knowledge, web_search, call_api, calculate
    Max 5 reasoning steps before forced synthesis.
    """

    def __init__(self, tools: list, max_iters: int = 5):
        super().__init__()
        self.react = dspy.ReAct(
            signature="session_context, long_term_memory, question -> answer",
            tools=tools,
            max_iters=max_iters,
        )

    def forward(
        self,
        question: str,
        session_context: str,
        long_term_memory: str,
        tenant_id: str,
    ):
        return self.react(
            question=question,
            session_context=session_context,
            long_term_memory=long_term_memory,
        )


# Query classifier — routes to simple vs complex path
CLASSIFIER_PROMPT = """
Classify this query into exactly one category. Reply with one word only.

simple   = factual lookup, one piece of info needed
complex  = requires multiple reasoning steps or synthesis
tool     = requires external action (web search, API call, calculation)

Query: {query}
Category:"""

async def classify_query(query: str) -> str:
    resp = await litellm.acompletion(
        model="groq/llama-3.1-8b-instant",
        messages=[{"role": "user", "content": CLASSIFIER_PROMPT.format(query=query)}],
        max_tokens=5,
        temperature=0,
    )
    label = resp.choices[0].message.content.strip().lower()
    return label if label in ("simple", "complex", "tool") else "simple"
```

---

## Component 3 — Tool Registry + Executor

Tenants register custom tools (any HTTP endpoint). Built-in tools always available.

### PostgreSQL Tool Registry

```sql
CREATE TABLE tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,          -- LLM reads this to decide when to use
    endpoint_url TEXT,                  -- NULL for built-in tools
    method VARCHAR(8) DEFAULT 'GET',
    auth_header TEXT,                   -- encrypted, Fernet
    input_schema JSONB,                 -- JSON Schema for tool input
    output_schema JSONB,
    is_builtin BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, name)
);
```

### Built-In Tools

```python
# synapseos/cognitive/tools.py
import httpx
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

class ToolExecutor:

    BUILTIN_TOOLS = {
        "retrieve_knowledge": {
            "description": "Search the tenant knowledge base for relevant information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        "web_search": {
            "description": "Search the live web for current information not in the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
        "call_api": {
            "description": "Call a registered tenant API endpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "payload": {"type": "object"},
                },
                "required": ["tool_name"],
            },
        },
        "calculate": {
            "description": "Evaluate a mathematical expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate"},
                },
                "required": ["expression"],
            },
        },
    }

    async def execute(
        self,
        tool_name: str,
        tool_input: dict,
        tenant_id: str,
    ) -> str:

        if tool_name == "retrieve_knowledge":
            results = await hybrid_query(
                query=tool_input["query"],
                tenant_id=tenant_id,
                final_k=tool_input.get("top_k", 5),
            )
            return "\n\n".join(h.payload["text"] for h in results)

        elif tool_name == "web_search":
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(
                    url=f"https://search.brave.com/search?q={tool_input['query']}",
                    config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=15000),
                )
                return result.markdown.fit_markdown[:3000]   # cap at 3k chars

        elif tool_name == "calculate":
            # Safe eval — numbers + operators only
            expr = tool_input["expression"]
            allowed = set("0123456789+-*/()., ")
            if not all(c in allowed for c in expr):
                return "Error: unsafe expression"
            try:
                return str(eval(expr))   # noqa: S307
            except Exception as e:
                return f"Error: {e}"

        elif tool_name == "call_api":
            # Load tenant custom tool from DB
            tool = await db.fetchrow(
                "SELECT * FROM tools WHERE tenant_id=$1 AND name=$2 AND active=TRUE",
                tenant_id, tool_input["tool_name"]
            )
            if not tool:
                return "Error: tool not found"
            auth = cipher.decrypt(tool["auth_header"]).decode() if tool["auth_header"] else None
            headers = {"Authorization": auth} if auth else {}
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.request(
                    method=tool["method"],
                    url=tool["endpoint_url"],
                    json=tool_input.get("payload", {}),
                    headers=headers,
                )
                return resp.text[:3000]

        return "Error: unknown tool"
```

### Tool Use via LiteLLM Function Calling

```python
async def run_with_tools(
    question: str,
    context: str,
    tenant_id: str,
    available_tools: list[dict],
):
    messages = [
        {"role": "system", "content": (
            "You are a precise assistant with access to tools. "
            "Use tools when needed. Base answers on retrieved context."
        )},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]

    response = await litellm.acompletion(
        model="groq/llama-3.1-70b-versatile",   # larger model for tool reasoning
        messages=messages,
        tools=available_tools,
        tool_choice="auto",
    )

    # Execute tool calls in parallel
    tool_calls = response.choices[0].message.tool_calls or []
    if tool_calls:
        executor = ToolExecutor()
        results = await asyncio.gather(*[
            executor.execute(tc.function.name, json.loads(tc.function.arguments), tenant_id)
            for tc in tool_calls
        ])
        # Append tool results and get final response
        messages.append(response.choices[0].message)
        for tc, result in zip(tool_calls, results):
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        response = await litellm.acompletion(
            model="groq/llama-3.1-70b-versatile",
            messages=messages,
        )

    return response.choices[0].message.content
```

---

## Component 4 — Self-Reflection

Evaluates its own answer before returning. One retry with injected critique.

```python
# synapseos/cognitive/reflection.py

REFLECTION_PROMPT = """You are a strict answer quality judge.

Question: {question}
Context provided: {context}
Answer generated: {answer}

Evaluate on three criteria. Be harsh. Score each 0.0 to 1.0:
1. relevancy: Does the answer directly address the question?
2. faithfulness: Is every claim supported by the context? No hallucinations?
3. completeness: Is the answer complete or does it miss obvious parts?

Reply in JSON only:
{{"relevancy": 0.0, "faithfulness": 0.0, "completeness": 0.0, "critique": "what is wrong"}}"""

RETRY_PROMPT = """Your previous answer had issues: {critique}

Rewrite the answer addressing these issues. Be precise, grounded in context only.

Question: {question}
Context: {context}
Improved answer:"""

async def reflect_and_refine(
    question: str,
    context: str,
    answer: str,
    max_retries: int = 1,
    threshold: float = 0.7,
) -> tuple[str, dict]:
    """
    Evaluate answer quality. Retry with critique if below threshold.
    Returns (final_answer, reflection_scores).
    Fast model (Groq Llama-8b) keeps reflection latency ~200ms.
    """
    for attempt in range(max_retries + 1):
        reflection_resp = await litellm.acompletion(
            model="groq/llama-3.1-8b-instant",
            messages=[{
                "role": "user",
                "content": REFLECTION_PROMPT.format(
                    question=question,
                    context=context[:2000],   # cap context for speed
                    answer=answer,
                ),
            }],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0,
        )

        try:
            scores = json.loads(reflection_resp.choices[0].message.content)
        except Exception:
            break   # malformed JSON — return as-is

        combined = (
            0.4 * scores.get("faithfulness", 0.7) +
            0.3 * scores.get("relevancy", 0.7) +
            0.3 * scores.get("completeness", 0.7)
        )

        if combined >= threshold or attempt == max_retries:
            return answer, scores

        # Retry with critique injected
        retry_resp = await litellm.acompletion(
            model="groq/llama-3.1-8b-instant",
            messages=[{
                "role": "user",
                "content": RETRY_PROMPT.format(
                    critique=scores.get("critique", "Answer was incomplete"),
                    question=question,
                    context=context,
                ),
            }],
            max_tokens=800,
        )
        answer = retry_resp.choices[0].message.content

    return answer, scores
```

---

## Full Cognitive Engine — Orchestrator

```python
# synapseos/cognitive/engine.py
import asyncio
from dataclasses import dataclass

@dataclass
class CognitiveResponse:
    answer: str
    query_type: str              # simple | complex | tool
    steps_taken: int
    reflection_scores: dict
    memories_recalled: int
    tools_used: list[str]
    trace_id: str

async def cognitive_query(
    question: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    stream: bool = False,
) -> CognitiveResponse:

    # ── STEP 1: Memory Load ─────────────────────────────────
    session_ctx, long_term_memory = await asyncio.gather(
        load_session(session_id),
        load_memories(user_id, tenant_id, question),
    )

    session_str = "\n".join(
        f"{t['role'].upper()}: {t['content']}" for t in session_ctx[-6:]
    )

    # ── STEP 2: Classify ────────────────────────────────────
    query_type = await classify_query(question)

    # ── STEP 3: Execute ─────────────────────────────────────
    tools_used = []
    steps = 1

    if query_type == "simple":
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload["text"] for h in hits)
        answer = await generate(question, [context], tenant_id=tenant_id)

    elif query_type == "complex":
        react_agent = SynapseReAct(
            tools=build_dspy_tools(tenant_id),
            max_iters=5,
        )
        result = react_agent(
            question=question,
            session_context=session_str,
            long_term_memory=long_term_memory,
            tenant_id=tenant_id,
        )
        answer = result.answer
        steps = len(result.trajectory) if hasattr(result, "trajectory") else 3
        context = ""

    elif query_type == "tool":
        tenant_tools = await load_tenant_tools(tenant_id)
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload["text"] for h in hits)
        answer = await run_with_tools(question, context, tenant_id, tenant_tools)
        tools_used = extract_used_tools(answer)

    # ── STEP 4: Self-Reflect ────────────────────────────────
    final_answer, reflection_scores = await reflect_and_refine(
        question=question,
        context=context if query_type != "complex" else long_term_memory,
        answer=answer,
        threshold=0.7,
    )

    # ── STEP 5: Memory Write ────────────────────────────────
    messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": final_answer},
    ]
    await asyncio.gather(
        append_session(session_id, "user", question),
        append_session(session_id, "assistant", final_answer),
        write_memory(user_id, tenant_id, messages),   # mem0 extracts facts
    )

    return CognitiveResponse(
        answer=final_answer,
        query_type=query_type,
        steps_taken=steps,
        reflection_scores=reflection_scores,
        memories_recalled=len(long_term_memory.split("\n")) if long_term_memory else 0,
        tools_used=tools_used,
        trace_id="",   # attached by Langfuse middleware
    )
```

---

## Updated API — Cognitive Endpoint

```
POST /v1/query         — existing (simple RAG, no memory)
POST /v1/think         — NEW (full cognitive engine: memory + reasoning + tools + reflection)
```

### POST /v1/think

```json
{
  "question": "What was the ROI on our Meta campaign last quarter, and how does it compare to Google?",
  "session_id": "sess-abc123",
  "user_id": "user-xyz",
  "stream": true
}
```

**Response** (SSE):
```
data: {"chunk": "Based on your Q3 reports and our previous discussion about "}
data: {"chunk": "campaign performance, Meta achieved 3.2x ROI while Google "}
data: {"chunk": "delivered 2.8x..."}
data: {
  "done": true,
  "query_type": "complex",
  "steps_taken": 3,
  "memories_recalled": 2,
  "tools_used": ["retrieve_knowledge"],
  "reflection": {"faithfulness": 0.91, "relevancy": 0.88, "completeness": 0.85},
  "trace_id": "lf-abc123"
}
```

---

## RAM Budget Impact (Cognitive Layer)

| Addition | RAM Delta |
|---|---|
| mem0 (uses existing Qdrant + PG) | +0 MB (shares infrastructure) |
| DSPy ReAct (CPU reasoning) | +200 MB peak (per active session) |
| Tool executor (httpx) | +50 MB |
| Reflection (Groq API, no local model) | +0 MB (external API call) |
| Session cache (KeyDB) | +0 MB (existing) |
| **Total delta** | **+~250 MB peak** |

Cognitive layer runs on Groq (external API) for classification + reflection — zero additional RAM on Oracle ARM. Only DSPy ReAct reasoning graph is in-memory.

---

## Latency Budget — Cognitive Path (no HyDE)

| Step | Latency |
|---|---|
| Memory load (KeyDB + mem0 Qdrant) | ~30ms |
| Query classification (Groq 8b) | ~100ms |
| Hybrid retrieval | ~235ms |
| Tool execution (if needed) | +50–500ms |
| Generation (Groq streaming) | ~300ms TTFT |
| Self-reflection (Groq 8b) | ~200ms |
| Memory write (async, non-blocking) | 0ms (fire-and-forget) |
| **Total (simple path + reflect)** | **~865ms P95** |
| **Total (tool path)** | **~1200ms P95** |
| **Total (complex ReAct, 3 steps)** | **~2000ms P95** |

Cloudflare Workers KV cache absorbs repeated queries — cognitive path only runs on cache miss.

---

## Phase 3 Build Order

```
Week 1 — Memory
  → pip install mem0ai
  → Create synapse_memory Qdrant collection
  → Implement load_memories / write_memory / session cache
  → Test: ask same question twice → second answer uses memory

Week 2 — Reflection
  → Implement reflect_and_refine
  → Wire into /v1/query as always-on (adds ~200ms)
  → Tune threshold 0.7 — log retry rate

Week 3 — Tool Registry + Executor
  → Create tools PostgreSQL table
  → Implement 4 built-in tools
  → Wire LiteLLM function calling
  → Test with web_search + retrieve_knowledge combo

Week 4 — Multi-Step Reasoning + Full Orchestrator
  → Implement classify_query
  → Wire DSPy ReAct with tools
  → Implement cognitive_query orchestrator
  → Launch POST /v1/think endpoint
  → End-to-end test: complex multi-step query with memory + tools + reflection
```
