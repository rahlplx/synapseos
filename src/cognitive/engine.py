"""
L7 — Cognitive Engine Orchestrator
Routes: simple → fast RAG | complex → enriched generation | tool → LiteLLM function calling | graph → entity aggregation
All paths end in self-reflection. Memory writes are non-blocking (fire-and-forget via _fire_and_forget).
CRAG: retrieval confidence gate prevents hallucination on weak context.
"""
import asyncio
import logging
from dataclasses import dataclass, field

from src.cognitive.memory import load_memories, write_memory, load_session, append_session
from src.cognitive.planner import classify_query
from src.cognitive.reflection import reflect_and_refine
from src.cognitive.tools import BUILTIN_SCHEMAS
from src.core.retrieval import hybrid_query, hybrid_query_with_retry
from src.core.generation import generate, fast_complete
from src.core.ingestion import _fire_and_forget

logger = logging.getLogger(__name__)


@dataclass
class CognitiveResponse:
    """Complete response from the cognitive engine."""
    answer: str
    query_type: str               # simple | complex | tool | graph
    steps_taken: int = 1
    reflection_scores: dict = field(default_factory=dict)
    memories_recalled: int = 0
    tools_used: list = field(default_factory=list)
    trace_id: str = ""
    confidence: str = "high"      # CRAG confidence: "high" or "low"


async def _graph_query(question: str, tenant_id: str) -> str:
    """Entity aggregation query using PostgreSQL entities table (LazyGraphRAG pattern).
    Steps: Extract entities → Query entities table → Combine with hybrid search.
    Cost: +1 Groq 8b call (~$0.0001), +1 PG query.
    """
    import json

    # Step 1: Extract entities from the question
    entity_prompt = f"""Extract the key entities (names, topics, categories) from this question.
Reply JSON only: {{"entities": [{{"name": "", "type": ""}}]}}

Question: {question}"""

    try:
        raw = await fast_complete(entity_prompt, max_tokens=200, json_mode=True)
        parsed = json.loads(raw)
        entities = parsed.get("entities", [])
    except Exception as e:
        logger.warning(f"[graph] Entity extraction failed: {type(e).__name__}: {e}")
        entities = []

    if not entities:
        hits = await hybrid_query(question, tenant_id)
        return "\n\n".join(h.payload.get("text", "") for h in hits)

    # Step 2: Query entities table
    from src.core.db import get_pool

    entity_context_parts = []
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for entity in entities[:5]:
                name = entity.get("name", "")
                if not name:
                    continue
                rows = await conn.fetch("""
                    SELECT entity_name, entity_type, document_ids, mention_count, metadata
                    FROM entities
                    WHERE tenant_id = $1 AND entity_name ILIKE $2
                    ORDER BY mention_count DESC LIMIT 10
                """, tenant_id, f"%{name}%")

                for row in rows:
                    doc_count = len(row["document_ids"]) if row["document_ids"] else 0
                    entity_context_parts.append(
                        f"- {row['entity_name']} ({row['entity_type']}): "
                        f"mentioned in {doc_count} documents, {row['mention_count']} times"
                    )
    except Exception as e:
        logger.warning(f"[graph] Entity query failed: {type(e).__name__}: {e}")

    # Step 3: Combine with hybrid search
    hits = await hybrid_query(question, tenant_id)
    knowledge = "\n\n".join(h.payload.get("text", "") for h in hits)

    if entity_context_parts:
        entity_summary = "Entity relationships found:\n" + "\n".join(entity_context_parts)
        return f"{entity_summary}\n\n---\n\nRetrieved knowledge:\n{knowledge}"
    return knowledge


async def cognitive_query(
    question: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    tenant_api_key: str = None,
    stream: bool = False,
) -> CognitiveResponse:
    """Full cognitive query pipeline:
    1. Memory Load (parallel) → 2. Classify → 3. Execute path → 4. Self-Reflect → 5. Memory Write
    """

    # ── STEP 1: Memory Load (parallel) ──
    session_turns, long_term_memory = await asyncio.gather(
        load_session(session_id),
        load_memories(user_id, tenant_id, question),
    )
    session_str = "\n".join(
        f"{t['role'].upper()}: {t['content']}" for t in session_turns[-6:]
    )
    memories_count = len(long_term_memory.split("\n")) if long_term_memory else 0

    # ── STEP 2: Classify ──
    query_type = await classify_query(question)
    tools_used: list[str] = []
    steps = 1
    context = ""
    confidence = "high"

    # ── STEP 3: Execute ──
    if query_type == "simple":
        hits, confidence = await hybrid_query_with_retry(question, tenant_id)
        context = "\n\n".join(h.payload.get("text", "") for h in hits)

        if confidence == "low":
            logger.info(f"[CRAG] Low confidence for simple query: {question[:80]}")
            try:
                from src.cognitive.tools import ToolExecutor
                web_result = await ToolExecutor().execute("web_search", {"query": question}, tenant_id)
                if web_result and len(web_result) > 50:
                    context = f"Web search result:\n{web_result}\n\nKnowledge base:\n{context}"
            except Exception as e:
                logger.warning(f"[CRAG] Web fallback failed: {type(e).__name__}: {e}")

        answer = await generate(question, [context], tenant_api_key)

    elif query_type == "complex":
        hits, confidence = await hybrid_query_with_retry(question, tenant_id)
        knowledge = "\n\n".join(h.payload.get("text", "") for h in hits)
        full_ctx = f"Session:\n{session_str}\n\nMemory:\n{long_term_memory}\n\nKnowledge:\n{knowledge}"
        answer = await generate(question, [full_ctx], tenant_api_key)
        context = knowledge
        steps = 2

    elif query_type == "graph":
        context = await _graph_query(question, tenant_id)
        full_ctx = f"Session:\n{session_str}\n\nMemory:\n{long_term_memory}\n\nEntity Relationships:\n{context}"
        answer = await generate(question, [full_ctx], tenant_api_key)
        steps = 2

    elif query_type == "tool":
        hits, confidence = await hybrid_query_with_retry(question, tenant_id)
        context = "\n\n".join(h.payload.get("text", "") for h in hits)

        try:
            from src.cognitive.generation_tools import generate_with_tools
            answer, tools_used = await generate_with_tools(
                question=question,
                context=f"Session:\n{session_str}\n\nMemory:\n{long_term_memory}\n\nKnowledge:\n{context}",
                available_tools=BUILTIN_SCHEMAS,
                tenant_api_key=tenant_api_key,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning(f"[non-critical] generate_with_tools failed, falling back: {type(e).__name__}: {e}")
            answer = await generate(question, [context], tenant_api_key)
            tools_used = ["retrieve_knowledge"]
        steps = 2

    else:
        # Default fallback — simple path
        hits, confidence = await hybrid_query_with_retry(question, tenant_id)
        context = "\n\n".join(h.payload.get("text", "") for h in hits)
        answer = await generate(question, [context], tenant_api_key)

    # ── STEP 4: Self-Reflect ──
    final_answer, scores = await reflect_and_refine(
        question=question,
        context=context if context else long_term_memory,
        answer=answer,
        threshold=0.7,
        max_retries=1,
    )

    # ── STEP 5: Memory Write (fire-and-forget — NEVER await) ──
    messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": final_answer},
    ]
    _fire_and_forget(write_memory(user_id, tenant_id, messages))
    _fire_and_forget(append_session(session_id, "user", question))
    _fire_and_forget(append_session(session_id, "assistant", final_answer))

    return CognitiveResponse(
        answer=final_answer,
        query_type=query_type,
        steps_taken=steps,
        reflection_scores=scores,
        memories_recalled=memories_count,
        tools_used=tools_used,
        confidence=confidence,
    )
