"""POST /v1/query — Fast hybrid RAG (~235ms target) with CRAG confidence gate + self-reflection."""
import time
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.core.retrieval import hybrid_query_with_confidence
from src.core.generation import generate_stream, generate
from src.cognitive.reflection import reflect_and_refine

router = APIRouter()
logger = logging.getLogger(__name__)

# CRAG: retrieval confidence threshold — if top result scores below this,
# flag as "low confidence" and suggest query refinement or web search fallback.
RETRIEVAL_CONFIDENCE_THRESHOLD = 0.35


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    stream: bool = True
    use_hyde: bool = False
    disable_web_fallback: bool = False  # Set True to skip CRAG web search fallback


@router.post("/query")
async def query_endpoint(body: QueryRequest, request: Request):
    tenant_id = request.state.tenant_id
    api_key = request.state.litellm_api_key
    trace_id = getattr(request.state, "langfuse_trace_id", "")
    start = time.perf_counter()

    # 1. Hybrid retrieval with CRAG confidence gate
    hits, confidence = await hybrid_query_with_confidence(
        body.question, tenant_id,
        final_k=body.top_k,
        use_hyde=body.use_hyde,
    )
    contexts = [h.payload.get("text", "") for h in hits]
    sources = [
        {
            "chunk_id": str(h.id),
            "text": h.payload.get("text", ""),
            "score": round(float(getattr(h, "score", 0.0)), 4),
            "source_url": h.payload.get("source_url", ""),
        }
        for h in hits
    ]

    # CRAG: If retrieval confidence is low, try web search fallback
    if confidence == "low" and not body.disable_web_fallback:
        logger.info(f"[CRAG] Low retrieval confidence for query: {body.question[:80]}")
        try:
            from src.cognitive.tools import ToolExecutor
            executor = ToolExecutor()
            web_result = await executor.execute(
                "web_search", {"query": body.question}, tenant_id
            )
            if web_result and len(web_result) > 50:
                contexts = [web_result] + contexts
                sources.insert(0, {
                    "chunk_id": "web_search",
                    "text": web_result[:500],
                    "score": 0.0,
                    "source_url": "web_search_fallback",
                })
        except Exception as e:
            logger.warning(f"[CRAG] Web search fallback failed: {type(e).__name__}: {e}")

    # CRAG: If still no useful context, return early instead of hallucinating
    if not contexts or all(len(c.strip()) < 20 for c in contexts):
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "answer": "I don't have enough information to answer this question confidently. Please try rephrasing or add more relevant documents to the knowledge base.",
            "sources": [],
            "trace_id": trace_id,
            "latency_ms": latency_ms,
            "reflection_scores": {},
            "retried": False,
            "confidence": "low",
        }

    context_str = "\n\n---\n\n".join(contexts)

    # 2. Streaming path (collect → reflect → re-stream)
    if body.stream:
        async def reflect_and_stream():
            # Collect full answer first
            full_answer = ""
            async for chunk_bytes in generate_stream(body.question, contexts, api_key):
                # chunk_bytes is already "data: {...}\n\n" — extract text
                try:
                    raw = chunk_bytes.replace("data: ", "").strip()
                    payload = json.loads(raw)
                    if "chunk" in payload:
                        full_answer += payload["chunk"]
                except Exception as e:
                    logger.debug(f"[SSE] Non-parseable chunk skipped: {type(e).__name__}")

            # Reflect on collected answer
            try:
                final_answer, scores = await reflect_and_refine(
                    body.question, context_str, full_answer
                )
            except Exception as e:
                logger.warning(f"[non-critical] Reflection failed in stream: {type(e).__name__}: {e}")
                final_answer, scores = full_answer, {}

            # Stream the (potentially improved) answer token by token
            for char in final_answer:
                yield f"data: {json.dumps({'chunk': char})}\n\n"

            latency_ms = int((time.perf_counter() - start) * 1000)
            yield f"data: {json.dumps({'done': True, 'trace_id': trace_id, 'reflection_scores': scores, 'latency_ms': latency_ms, 'sources': sources, 'confidence': confidence})}\n\n"

        return StreamingResponse(reflect_and_stream(), media_type="text/event-stream")

    # 3. Non-streaming path
    answer = await generate(body.question, contexts, api_key)

    try:
        final_answer, reflection_scores = await reflect_and_refine(
            body.question, context_str, answer
        )
    except Exception as e:
        logger.warning(f"[non-critical] Reflection failed: {type(e).__name__}: {e}")
        final_answer, reflection_scores = answer, {}

    latency_ms = int((time.perf_counter() - start) * 1000)
    retried = reflection_scores.get("combined", 1.0) < 0.7

    return {
        "answer": final_answer,
        "sources": sources,
        "trace_id": trace_id,
        "latency_ms": latency_ms,
        "reflection_scores": reflection_scores,
        "retried": retried,
        "confidence": confidence,
    }
