"""
TenantMiddleware — Rate limiting + BYOK key injection
Evaluated BEFORE any ONNX/embedding work to prevent CPU starvation.
Public paths (/health, /docs) are skipped entirely.
"""
import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.clients import get_keydb, get_cipher

# Paths that don't require tenant authentication
PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

# Atomic incr + expire via Lua script (prevents key leak on crash)
_LUA_INCR_EXPIRE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


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
        keydb = get_keydb()
        window = int(time.time() // 60)
        limit_key = f"rate:{tenant_id}:{window}"
        count = await keydb.eval(_LUA_INCR_EXPIRE, 1, limit_key, 60)

        rpm_limit = int(await keydb.get(f"tenant:{tenant_id}:rpm") or 60)
        if count > rpm_limit:
            raise HTTPException(429, f"Rate limit exceeded ({rpm_limit} RPM)")

        # ── 3. BYOK Key Injection ──
        encrypted = await keydb.get(f"tenant:{tenant_id}:api_key")
        if encrypted:
            try:
                request.state.litellem_api_key = get_cipher().decrypt(encrypted).decode()
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    f"[security] BYOK Fernet decrypt failed for tenant={tenant_id}"
                )
                request.state.litellm_api_key = None
        else:
            request.state.litellm_api_key = None

        # Attach tenant_id for downstream routes
        request.state.tenant_id = tenant_id
        return await call_next(request)
