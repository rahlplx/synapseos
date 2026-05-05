"""Langfuse trace middleware — attaches trace to every /v1/ request.
Compatible with Langfuse v4+ (no decorators module, uses start_observation).
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from langfuse import Langfuse

from src.core.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

langfuse = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST,
)


class LangfuseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        tenant = getattr(request.state, "tenant_id", "unknown")

        trace_id = langfuse.create_trace_id()
        observation = langfuse.start_observation(
            name=request.url.path,
            trace_id=trace_id,
            metadata={"tenant": tenant, "method": request.method},
        )

        request.state.langfuse_trace_id = trace_id

        try:
            response = await call_next(request)
            observation.update(output={"status": response.status_code})
        except Exception as e:
            observation.update(output={"status": 500, "error": str(e)})
            raise
        finally:
            langfuse.flush()

        return response
