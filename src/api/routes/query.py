"""POST /v1/query — Fast hybrid RAG (~235ms target) with CRAG confidence gate + self-reflection."""
import json
import logging
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.api.models import QueryRequest, _latency_ms
from src.core.retrieval import hybrid_query_with_retry
from src.core.generation import generate_stream, generate
from src.cognitive.reflection import reflect_and_refine

router = APIRouter(tags=["query"])
logger = logging.getLogger(__name__)


@router.post("/query", summary="Fast RAG query", response_description="Answer with sources and confidence")
async def query_endpoint(body: QueryRequest, request: Request):
    """Fast hybrid RAG endpoint (~235ms target).

    Pipeline: Hybrid retrieval (dense + BM25 + RRF + rerank) → CRAG confidence gate →
    Self-reflection → Answer.

    If retrieval confidence is low, automatically tries web search fallback
    (CRAG pattern) to prevent hallucination from weak context.
    """
    tenant_id = request.state.tenant_id
    api_key = request.state.litellm_api_key
    trace_id = getattr(request.state, "langfuse_trace_id", "")
    start = time.perf_counter()

    # 1. Hybrid retrieval with CRAG confidence gate + query rewrite
    hits, confidence = await hybrid_query_with_retry(
        body.question, tenant_id,
        final_k=body.top_k,
        use_hyde=body.use_hyde,
    )
    contexts = [h.payload.get("text", "") for h in hits]
    sources = [
        {
            "chunk_id": str(h.id),
            "text": h.payload.get("text", ""),
            "score": round(h.payload.get("_rerank_score", float(getattr(h, "score", 0.0))), 4),
            "source_url": h.payload.get("source_url", ""),
        }
        for h in hits
    ]

    # 2. CRAG: If retrieval confidence is low, try web search fallback
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

    # 3. CRAG: If still no useful context, return early instead of hallucinating
    if not contexts or all(len(c.strip()) < 20 for c in contexts):
        return {
            "answer": "I don't have enough information to answer this question confidently. Please try rephrasing or add more relevant documents to the knowledge base.",
            "sources": [],
            "trace_id": trace_id,
            "latency_ms": _latency_ms(start),
            "reflection_scores": {},
            "retried": False,
            "confidence": "low",
        }

    context_str = "\n\n---\n\n".join(contexts)

    # 4. Streaming path — stream tokens immediately, reflect after stream completes
    if body.stream:
        async def stream_and_reflect():
            full_answer = ""
            async for chunk_bytes in generate_stream(body.question, contexts, api_key):
                try:
                    raw = chunk_bytes.replace("data: ", "").strip()
                    payload = json.loads(raw)
                    if "chunk" in payload:
                        full_answer += payload["chunk"]
                except Exception:
                    logger.debug("[SSE] Non-parseable chunk skipped")
                yield chunk_bytes if chunk_bytes.endswith("\n\n") else chunk_bytes + "\n\n"

            # After stream completes, run reflection and send metadata
            try:
                _, scores = await reflect_and_refine(body.question, context_str, full_answer)
            except Exception as e:
                logger.warning(f"[non-critical] Reflection failed in stream: {type(e).__name__}: {e}")
                scores = {}

            yield f"data: {json.dumps({'done': True, 'trace_id': trace_id, 'reflection_scores': scores, 'latency_ms': _latency_ms(start), 'sources': sources, 'confidence': confidence})}\n\n"

        return StreamingResponse(stream_and_reflect(), media_type="text/event-stream")

    # 5. Non-streaming path
    answer = await generate(body.question, contexts, api_key)

    try:
        final_answer, reflection_scores = await reflect_and_refine(
            body.question, context_str, answer
        )
    except Exception as e:
        logger.warning(f"[non-critical] Reflection failed: {type(e).__name__}: {e}")
        final_answer, reflection_scores = answer, {}

    retried = reflection_scores.get("combined", 1.0) < 0.7

    return {
        "answer": final_answer,
        "sources": sources,
        "trace_id": trace_id,
        "latency_ms": _latency_ms(start),
        "reflection_scores": reflection_scores,
        "retried": retried,
        "confidence": confidence,
    }
