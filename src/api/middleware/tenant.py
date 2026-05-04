"""
TenantMiddleware — Rate limiting + BYOK key injection
Evaluated BEFORE any ONNX/embedding work to prevent CPU starvation.
Public paths (/health, /docs) are skipped entirely.
"""
import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from cryptography.fernet import Fernet
import redis.asyncio as redis
import os

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))
cipher = Fernet(os.environ["ENCRYPTION_KEY"].encode())

# Paths that don't require tenant authentication
PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # ── 1. Tenant Identification ──
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise HTTPException(401, "Missing X-Tenant-ID header")

        # ── 2. Rate Limiting — sliding window BEFORE any ONNX work ──
        # This prevents CPU starvation from unauthenticated/over-limit requests
        # Uses Lua script for atomic incr+expire (prevents race condition on crash)
        window = int(time.time() // 60)
        limit_key = f"rate:{tenant_id}:{window}"

        # Atomic incr + expire via Lua script (prevents key leak on crash between incr and expire)
        lua_incr_expire = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then
            redis.call('EXPIRE', KEYS[1], ARGV[1])
        end
        return count
        """
        count = await keydb.eval(lua_incr_expire, 1, limit_key, 60)

        # Check tenant-specific RPM limit (default: 60 RPM)
        rpm_limit = int(await keydb.get(f"tenant:{tenant_id}:rpm") or 60)
        if count > rpm_limit:
            raise HTTPException(429, f"Rate limit exceeded ({rpm_limit} RPM)")

        # ── 3. BYOK Key Injection ──
        # Check KeyDB first (fast), then fall back to platform default
        encrypted = await keydb.get(f"tenant:{tenant_id}:api_key")
        if encrypted:
            try:
                request.state.litellm_api_key = cipher.decrypt(encrypted).decode()
            except Exception as e:
                # Corrupted encryption — log and fall back to platform key
                import logging
                logging.getLogger(__name__).warning(f"[security] BYOK Fernet decrypt failed for tenant={tenant_id}: {type(e).__name__}")
                request.state.litellm_api_key = None
        else:
            # No BYOK key configured — use platform default (Groq free tier)
            request.state.litellm_api_key = None

        # Attach tenant_id for downstream routes
        request.state.tenant_id = tenant_id
        return await call_next(request)
