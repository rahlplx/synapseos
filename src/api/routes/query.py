"""POST /v1/query — Fast hybrid RAG (~235ms target) with self-reflection."""
import time
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.core.retrieval import hybrid_query
from src.core.generation import generate_stream, generate
from src.cognitive.reflection import reflect_and_refine

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    stream: bool = True
    use_hyde: bool = False


@router.post("/query")
async def query_endpoint(body: QueryRequest, request: Request):
    tenant_id = request.state.tenant_id
    api_key = request.state.litellm_api_key
    trace_id = getattr(request.state, "langfuse_trace_id", "")
    start = time.perf_counter()

    # 1. Hybrid retrieval
    hits = await hybrid_query(
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
                except Exception:
                    pass

            # Reflect on collected answer
            try:
                final_answer, scores = await reflect_and_refine(
                    body.question, context_str, full_answer
                )
            except Exception:
                final_answer, scores = full_answer, {}

            # Stream the (potentially improved) answer token by token
            for char in final_answer:
                yield f"data: {json.dumps({'chunk': char})}\n\n"

            latency_ms = int((time.perf_counter() - start) * 1000)
            yield f"data: {json.dumps({'done': True, 'trace_id': trace_id, 'reflection_scores': scores, 'latency_ms': latency_ms, 'sources': sources})}\n\n"

        return StreamingResponse(reflect_and_stream(), media_type="text/event-stream")

    # 3. Non-streaming path
    answer = await generate(body.question, contexts, api_key)

    try:
        final_answer, reflection_scores = await reflect_and_refine(
            body.question, context_str, answer
        )
    except Exception:
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
    }
