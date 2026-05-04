"""Langfuse trace middleware — attaches trace to every /v1/ request.
Compatible with Langfuse v4+ (no decorators module, uses start_observation).
"""
import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from langfuse import Langfuse

langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    host=os.environ.get("LANGFUSE_HOST", "http://langfuse:3100"),
)


class LangfuseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only trace API requests, not health/docs
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        tenant = getattr(request.state, "tenant_id", "unknown")

        # Langfuse v4: use start_observation for tracing
        trace_id = langfuse.create_trace_id()
        observation = langfuse.start_observation(
            name=request.url.path,
            trace_id=trace_id,
            metadata={"tenant": tenant, "method": request.method},
        )

        # Store trace_id on request state for downstream use
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
