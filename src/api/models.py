"""
Shared Pydantic models and response helpers for API routes.
Eliminates duplicate field definitions and standardizes error format.
"""
import time
import logging
from typing import Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─── Base Request Models ───────────────────────────────────────────────────────

class QuestionBase(BaseModel):
    """Base model for all endpoints that accept a question."""
    question: str = Field(
        ...,
        max_length=2000,
        description="Query question (max 2000 chars)",
        examples=["What is the revenue growth rate for Q3 2024?"],
    )


class QueryRequest(QuestionBase):
    """POST /v1/query — Fast hybrid RAG with CRAG confidence gate."""
    top_k: int = Field(default=5, ge=1, le=20, description="Number of retrieval results")
    stream: bool = Field(default=True, description="Stream tokens via SSE")
    use_hyde: bool = Field(default=False, description="Enable HyDE (adds ~1s latency)")
    disable_web_fallback: bool = Field(default=False, description="Skip CRAG web search fallback")


class ThinkRequest(QuestionBase):
    """POST /v1/think — Full cognitive engine (memory + reasoning + tools + reflection)."""
    session_id: str = Field(..., description="Session ID for conversation continuity")
    user_id: str = Field(..., description="User ID for memory isolation")
    stream: bool = Field(default=False, description="Stream answer via SSE")


class IngestRequest(BaseModel):
    """POST /v1/ingest — Queue document ingestion."""
    urls: list[str] = Field(
        ..., max_length=10,
        description="List of URLs to ingest (max 10)",
        examples=[["https://example.com/report.pdf"]],
    )
    metadata: dict = Field(default_factory=dict, description="Optional metadata to attach")


class FeedbackRequest(BaseModel):
    """POST /v1/feedback — Thumbs up/down on a trace."""
    trace_id: str = Field(..., description="Langfuse trace ID from the response")
    rating: int = Field(..., description="+1 (thumbs up) or -1 (thumbs down)")


class RegisterKeyRequest(BaseModel):
    """POST /v1/keys — Register a BYOK API key."""
    provider: str = Field(
        ...,
        description="LLM provider name (e.g. 'groq', 'openrouter', 'anthropic')",
        examples=["groq"],
    )
    api_key: str = Field(
        ...,
        min_length=8,
        max_length=512,
        description="API key for the provider (stored encrypted with Fernet)",
    )


class RegisterToolRequest(BaseModel):
    """POST /v1/tools — Register a custom tenant tool."""
    name: str = Field(..., min_length=1, max_length=64, description="Tool name (unique per tenant)")
    endpoint_url: str = Field(..., description="HTTP endpoint URL for the tool")
    method: str = Field(default="GET", description="HTTP method (GET, POST, PUT, DELETE)")
    auth_header: str = Field(default="", description="Authorization header value (stored encrypted)")
    description: str = Field(default="", max_length=500, description="Human-readable tool description")
    active: bool = Field(default=True, description="Whether the tool is active")


# ─── Standardized Error Response ───────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Consistent error format across all endpoints."""
    error: str
    detail: Optional[str] = None
    status_code: int


# ─── Response Helpers ──────────────────────────────────────────────────────────

def _latency_ms(start: float) -> int:
    """Calculate elapsed milliseconds since start timestamp."""
    return int((time.perf_counter() - start) * 1000)
