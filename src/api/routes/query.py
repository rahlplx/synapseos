"""POST /v1/query — Fast hybrid RAG (no memory, ~235ms target)"""
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.core.retrieval import hybrid_query
from src.core.generation import generate_stream, generate

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    stream: bool = True
    use_hyde: bool = False


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    trace_id: str = ""
    latency_ms: int = 0


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

    # 2. Build sources with scores
    sources = []
    for h in hits:
        sources.append({
            "chunk_id": str(h.id),
            "text": h.payload.get("text", ""),
            "score": getattr(h, "score", 0.0),
            "source_url": h.payload.get("source_url", ""),
        })

    if body.stream:
        # Streaming: SSE format — data: {"chunk": "..."}\n\n
        return StreamingResponse(
            generate_stream(body.question, contexts, api_key, sources=sources),
            media_type="text/event-stream",
        )

    # Non-streaming: full JSON response
    answer = await generate(body.question, contexts, api_key)
    latency_ms = int((time.perf_counter() - start) * 1000)

    return QueryResponse(
        answer=answer,
        sources=sources,
        trace_id=trace_id,
        latency_ms=latency_ms,
    )
