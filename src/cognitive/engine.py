"""
L7 — Cognitive Engine Orchestrator
Routes: simple → fast RAG | complex → enriched generation | tool → LiteLLM function calling
All paths end in self-reflection. Memory writes are non-blocking (asyncio.create_task).
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from src.cognitive.memory import load_memories, write_memory, load_session, append_session
from src.cognitive.planner import classify_query
from src.cognitive.reflection import reflect_and_refine
from src.cognitive.tools import ToolExecutor, BUILTIN_SCHEMAS
from src.core.retrieval import hybrid_query
from src.core.generation import generate


@dataclass
class CognitiveResponse:
    """Complete response from the cognitive engine."""
    answer: str
    query_type: str               # simple | complex | tool
    steps_taken: int = 1
    reflection_scores: dict = field(default_factory=dict)
    memories_recalled: int = 0
    tools_used: list = field(default_factory=list)
    trace_id: str = ""


async def cognitive_query(
    question: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    stream: bool = False,
) -> CognitiveResponse:
    """Full cognitive query pipeline:
    1. Memory Load (session + long-term, in parallel)
    2. Classify query (simple/complex/tool)
    3. Execute appropriate path
    4. Self-reflect on answer
    5. Write memory (non-blocking)
    """

    # ── STEP 1: Memory Load (parallel) ──────────────────────────────────
    session_turns, long_term_memory = await asyncio.gather(
        load_session(session_id),
        load_memories(user_id, tenant_id, question),
    )
    session_str = "\n".join(
        f"{t['role'].upper()}: {t['content']}" for t in session_turns[-6:]
    )
    memories_count = len(long_term_memory.split("\n")) if long_term_memory else 0

    # ── STEP 2: Classify ────────────────────────────────────────────────
    query_type = await classify_query(question)
    tools_used: list[str] = []
    steps = 1
    context = ""

    # ── STEP 3: Execute ─────────────────────────────────────────────────
    if query_type == "simple":
        # Fast RAG path: retrieve → generate
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload.get("text", "") for h in hits)
        answer = await generate(question, [context])

    elif query_type == "complex":
        # Enriched path: retrieve + session + memory context
        hits = await hybrid_query(question, tenant_id)
        knowledge = "\n\n".join(h.payload.get("text", "") for h in hits)
        full_ctx = f"Session:\n{session_str}\n\nMemory:\n{long_term_memory}\n\nKnowledge:\n{knowledge}"
        answer = await generate(question, [full_ctx])
        context = knowledge  # Use knowledge for reflection, not full context
        steps = 2

    elif query_type == "tool":
        # Tool path: retrieve + LiteLLM function calling with parallel tool execution
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload.get("text", "") for h in hits)

        try:
            from src.cognitive.generation_tools import generate_with_tools
            answer, tools_used = await generate_with_tools(
                question=question,
                context=f"Session:\n{session_str}\n\nMemory:\n{long_term_memory}\n\nKnowledge:\n{context}",
                available_tools=BUILTIN_SCHEMAS,
                tenant_api_key=None,  # BYOK key injected by middleware
            )
        except Exception:
            # Fallback: generate without tools if function calling fails
            answer = await generate(question, [context])
            tools_used = ["retrieve_knowledge"]
        steps = 2

    else:
        # Default fallback — simple path
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload.get("text", "") for h in hits)
        answer = await generate(question, [context])

    # ── STEP 4: Self-Reflect ────────────────────────────────────────────
    final_answer, scores = await reflect_and_refine(
        question=question,
        context=context if context else long_term_memory,
        answer=answer,
        threshold=0.7,
        max_retries=1,
    )

    # ── STEP 5: Memory Write (non-blocking — NEVER await) ──────────────
    messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": final_answer},
    ]
    # All writes use create_task — they run in background, never block response
    asyncio.create_task(write_memory(user_id, tenant_id, messages))
    asyncio.create_task(append_session(session_id, "user", question))
    asyncio.create_task(append_session(session_id, "assistant", final_answer))

    return CognitiveResponse(
        answer=final_answer,
        query_type=query_type,
        steps_taken=steps,
        reflection_scores=scores,
        memories_recalled=memories_count,
        tools_used=tools_used,
    )
