"""POST /v1/think — Full cognitive engine (memory + reasoning + tools + reflection)"""
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.api.models import ThinkRequest, _latency_ms
from src.cognitive.engine import cognitive_query

router = APIRouter(tags=["cognitive"])


@router.post("/think", summary="Cognitive thinking query", response_description="Deep answer with reasoning steps")
async def think_endpoint(body: ThinkRequest, request: Request):
    """Full cognitive engine endpoint (~865ms target).

    Pipeline: Memory load (parallel) → Query classification →
    Route to simple/complex/tool/graph path → Self-reflection → Memory write.

    Supports 4 query types:
    - **simple**: Fast RAG with CRAG confidence gate
    - **complex**: Multi-step reasoning with session + memory context
    - **tool**: LiteLLM function calling with parallel tool execution
    - **graph**: Cross-document entity aggregation (LazyGraphRAG pattern)
    """
    tenant_id = request.state.tenant_id
    api_key = getattr(request.state, "litellm_api_key", None)
    start = time.perf_counter()

    if body.stream:
        result = await cognitive_query(
            question=body.question,
            session_id=body.session_id,
            user_id=body.user_id,
            tenant_id=tenant_id,
            tenant_api_key=api_key,
            stream=False,
        )
        async def _stream_cognitive():
            yield f"data: {json.dumps({'chunk': result.answer})}\n\n"
            yield f"data: {json.dumps({
                'done': True,
                'query_type': result.query_type,
                'steps_taken': result.steps_taken,
                'reflection_scores': result.reflection_scores,
                'memories_recalled': result.memories_recalled,
                'tools_used': result.tools_used,
                'confidence': result.confidence,
            })}\n\n"

        return StreamingResponse(
            _stream_cognitive(),
            media_type="text/event-stream",
        )

    # Non-streaming: return full CognitiveResponse
    result = await cognitive_query(
        question=body.question,
        session_id=body.session_id,
        user_id=body.user_id,
        tenant_id=tenant_id,
        tenant_api_key=api_key,
    )

    return {
        "answer": result.answer,
        "query_type": result.query_type,
        "steps_taken": result.steps_taken,
        "reflection_scores": result.reflection_scores,
        "memories_recalled": result.memories_recalled,
        "tools_used": result.tools_used,
        "confidence": result.confidence,
        "latency_ms": _latency_ms(start),
    }
