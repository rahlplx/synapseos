"""POST /v1/think — Full cognitive engine (memory + reasoning + tools + reflection)"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.cognitive.engine import cognitive_query

router = APIRouter()


class ThinkRequest(BaseModel):
    question: str
    session_id: str
    user_id: str
    stream: bool = True


@router.post("/think")
async def think_endpoint(body: ThinkRequest, request: Request):
    tenant_id = request.state.tenant_id
    result = await cognitive_query(
        question=body.question,
        session_id=body.session_id,
        user_id=body.user_id,
        tenant_id=tenant_id,
    )
    return {
        "answer": result.answer,
        "query_type": result.query_type,
        "steps_taken": result.steps_taken,
        "reflection_scores": result.reflection_scores,
        "memories_recalled": result.memories_recalled,
        "tools_used": result.tools_used,
    }
