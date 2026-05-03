"""
TenantMiddleware — Rate limiting + BYOK key injection
Evaluated BEFORE any ONNX/embedding work to prevent CPU starvation.
"""
import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from cryptography.fernet import Fernet
import redis.asyncio as redis
import asyncpg
import os

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))
cipher = Fernet(os.environ["ENCRYPTION_KEY"].encode())

PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise HTTPException(401, "Missing X-Tenant-ID header")

        # 1. Rate limit — sliding window — before ANY ONNX work
        window = int(time.time() // 60)
        limit_key = f"rate:{tenant_id}:{window}"
        count = await keydb.incr(limit_key)
        if count == 1:
            await keydb.expire(limit_key, 60)
        rpm_limit = int(await keydb.get(f"tenant:{tenant_id}:rpm") or 60)
        if count > rpm_limit:
            raise HTTPException(429, "Tenant rate limit exceeded")

        # 2. BYOK key injection — AES-256 Fernet decrypt
        encrypted = await keydb.get(f"tenant:{tenant_id}:api_key")
        if encrypted:
            request.state.litellm_api_key = cipher.decrypt(encrypted).decode()
        else:
            request.state.litellm_api_key = None  # uses platform default

        request.state.tenant_id = tenant_id
        return await call_next(request)
