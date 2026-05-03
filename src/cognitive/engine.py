"""
L7 — Cognitive Engine Orchestrator
Routes: simple → fast RAG | complex → DSPy ReAct | tool → LiteLLM function calling
All paths end in self-reflection.
"""
import asyncio
from dataclasses import dataclass, field

from src.cognitive.memory import load_memories, write_memory, load_session, append_session
from src.cognitive.planner import classify_query, SynapseReAct
from src.cognitive.reflection import reflect_and_refine
from src.cognitive.tools import ToolExecutor, BUILTIN_SCHEMAS
from src.core.retrieval import hybrid_query
from src.core.generation import generate


@dataclass
class CognitiveResponse:
    answer: str
    query_type: str
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
) -> CognitiveResponse:

    # ── STEP 1: Memory Load ─────────────────────────────────
    session_turns, long_term_memory = await asyncio.gather(
        load_session(session_id),
        load_memories(user_id, tenant_id, question),
    )
    session_str = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in session_turns[-6:])
    memories_count = len(long_term_memory.split("\n")) if long_term_memory else 0

    # ── STEP 2: Classify ────────────────────────────────────
    query_type = await classify_query(question)
    tools_used = []
    steps = 1
    context = ""

    # ── STEP 3: Execute ─────────────────────────────────────
    if query_type == "simple":
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload["text"] for h in hits)
        answer = await generate(question, [context])

    elif query_type == "complex":
        # DSPy ReAct — TODO: wire full tool dspy functions in Phase 3
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload["text"] for h in hits)
        full_ctx = f"Session:\n{session_str}\n\nMemory:\n{long_term_memory}\n\nKnowledge:\n{context}"
        answer = await generate(question, [full_ctx])
        steps = 2

    elif query_type == "tool":
        hits = await hybrid_query(question, tenant_id)
        context = "\n\n".join(h.payload["text"] for h in hits)
        executor = ToolExecutor()
        # Phase 3: full LiteLLM function calling loop
        answer = await generate(question, [context])
        tools_used = ["retrieve_knowledge"]

    # ── STEP 4: Self-Reflect ────────────────────────────────
    final_answer, scores = await reflect_and_refine(question, context, answer)

    # ── STEP 5: Memory Write (non-blocking) ─────────────────
    messages = [{"role": "user", "content": question}, {"role": "assistant", "content": final_answer}]
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
