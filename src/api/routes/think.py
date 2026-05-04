"""POST /v1/think — Full cognitive engine (memory + reasoning + tools + reflection)"""
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from src.cognitive.engine import cognitive_query
from src.core.generation import generate_stream

router = APIRouter()


class ThinkRequest(BaseModel):
    question: str = Field(..., max_length=2000, description="Query question (max 2000 chars)")
    session_id: str
    user_id: str
    stream: bool = False


@router.post("/think")
async def think_endpoint(body: ThinkRequest, request: Request):
    tenant_id = request.state.tenant_id
    api_key = getattr(request.state, "litellm_api_key", None)
    start = time.perf_counter()

    if body.stream:
        # For streaming: run cognitive_query, then stream the answer
        result = await cognitive_query(
            question=body.question,
            session_id=body.session_id,
            user_id=body.user_id,
            tenant_id=tenant_id,
            tenant_api_key=api_key,
            stream=False,
        )
        # Stream the answer in SSE format
        async def _stream_cognitive():
            import json
            yield f"data: {json.dumps({'chunk': result.answer})}\n\n"
            yield f"data: {json.dumps({
                'done': True,
                'query_type': result.query_type,
                'steps_taken': result.steps_taken,
                'reflection_scores': result.reflection_scores,
                'memories_recalled': result.memories_recalled,
                'tools_used': result.tools_used,
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
    latency_ms = int((time.perf_counter() - start) * 1000)

    return {
        "answer": result.answer,
        "query_type": result.query_type,
        "steps_taken": result.steps_taken,
        "reflection_scores": result.reflection_scores,
        "memories_recalled": result.memories_recalled,
        "tools_used": result.tools_used,
        "latency_ms": latency_ms,
    }
