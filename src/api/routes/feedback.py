"""POST /v1/feedback — Thumbs up/down on a trace"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from langfuse import Langfuse

router = APIRouter()
langfuse = Langfuse()


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: int  # +1 or -1


@router.post("/feedback")
async def feedback_endpoint(body: FeedbackRequest, request: Request):
    """Submit thumbs up/down on a RAG response."""
    tenant_id = getattr(request.state, "tenant_id", "unknown")
    langfuse.score(
        trace_id=body.trace_id,
        name="user_feedback",
        value=body.rating,
        metadata={"tenant_id": tenant_id},
    )
    return {"recorded": True}
