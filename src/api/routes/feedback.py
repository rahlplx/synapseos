"""POST /v1/feedback — Thumbs up/down on a trace"""
from fastapi import APIRouter, Request
from langfuse import Langfuse

from src.api.models import FeedbackRequest

router = APIRouter(tags=["feedback"])
langfuse = Langfuse()


@router.post("/feedback", summary="Submit feedback", response_description="Confirmation of recorded feedback")
async def feedback_endpoint(body: FeedbackRequest, request: Request):
    """Submit thumbs up/down on a RAG response.

    Records user feedback in Langfuse for analytics and self-improvement.
    Use the `trace_id` from the query/think response to identify which
    answer the feedback applies to.
    """
    tenant_id = getattr(request.state, "tenant_id", "unknown")
    langfuse.score(
        trace_id=body.trace_id,
        name="user_feedback",
        value=body.rating,
        metadata={"tenant_id": tenant_id},
    )
    return {"recorded": True}
