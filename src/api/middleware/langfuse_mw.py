"""Langfuse trace middleware — attaches trace to every /v1/ request."""
import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from langfuse import Langfuse
from langfuse.decorators import langfuse_context

langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    host=os.environ.get("LANGFUSE_HOST", "http://langfuse:3100"),
)


class LangfuseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        tenant = getattr(request.state, "tenant_id", "unknown")
        trace = langfuse.trace(name=request.url.path, metadata={"tenant": tenant})
        langfuse_context.configure(trace=trace)
        try:
            response = await call_next(request)
            trace.update(output={"status": response.status_code})
        finally:
            langfuse.flush()
        return response
