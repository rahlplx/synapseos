"""POST /v1/query — Fast hybrid RAG (no memory, ~235ms)"""
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


@router.post("/query")
async def query_endpoint(body: QueryRequest, request: Request):
    tenant_id = request.state.tenant_id
    api_key = request.state.litellm_api_key

    hits = await hybrid_query(body.question, tenant_id, final_k=body.top_k, use_hyde=body.use_hyde)
    contexts = [h.payload["text"] for h in hits]

    if body.stream:
        return StreamingResponse(
            generate_stream(body.question, contexts, api_key),
            media_type="text/event-stream",
        )
    answer = await generate(body.question, contexts, api_key)
    return {"answer": answer, "sources": [{"text": h.payload["text"], "score": 0.0} for h in hits]}
