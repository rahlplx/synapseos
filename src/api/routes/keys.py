"""POST /v1/keys, DELETE /v1/keys — BYOK API key management.

Tenants register their own LLM API keys (Groq, OpenRouter, Anthropic, etc.).
Keys are encrypted at rest with Fernet and decrypted on-the-fly by TenantMiddleware.
"""
import logging
from fastapi import APIRouter, Request, HTTPException

from src.api.models import RegisterKeyRequest, ErrorResponse
from src.core.clients import get_keydb, get_cipher

router = APIRouter(tags=["keys"])
logger = logging.getLogger(__name__)


@router.post(
    "/keys",
    summary="Register BYOK API key",
    response_description="Confirmation of key registration",
    responses={400: {"model": ErrorResponse}},
)
async def register_key(body: RegisterKeyRequest, request: Request):
    """Register or rotate a BYOK API key for a specific provider.

    The key is encrypted with Fernet before storage in KeyDB.
    Only one key per provider per tenant — re-registering overwrites the existing key.
    The decrypted key is injected into `request.state.litellm_api_key` by
    TenantMiddleware on subsequent requests.

    Supported providers: groq, openrouter, anthropic, or any LiteLLM-compatible provider.
    """
    tenant_id = request.state.tenant_id
    keydb = get_keydb()

    try:
        cipher = get_cipher()
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    encrypted = cipher.encrypt(body.api_key.encode()).decode()
    key_key = f"tenant:{tenant_id}:api_key:{body.provider}"

    await keydb.set(key_key, encrypted)

    # Also set the default key (used by middleware for backward compatibility)
    if body.provider in ("groq", "default"):
        await keydb.set(f"tenant:{tenant_id}:api_key", encrypted)

    logger.info(f"[keys] BYOK key registered for tenant={tenant_id}, provider={body.provider}")
    return {"registered": True, "provider": body.provider}


@router.delete(
    "/keys/{provider}",
    summary="Delete BYOK API key",
    response_description="Confirmation of key deletion",
    responses={404: {"model": ErrorResponse}},
)
async def delete_key(provider: str, request: Request):
    """Delete a registered BYOK API key for a specific provider.

    After deletion, the tenant will fall back to the system default API key
    for the specified provider. Returns 404 if no key was registered.
    """
    tenant_id = request.state.tenant_id
    keydb = get_keydb()

    key_key = f"tenant:{tenant_id}:api_key:{provider}"
    existed = await keydb.delete(key_key)

    # Also clear default key if deleting groq/default
    if provider in ("groq", "default"):
        await keydb.delete(f"tenant:{tenant_id}:api_key")

    if not existed:
        raise HTTPException(404, f"No key registered for provider '{provider}'")

    logger.info(f"[keys] BYOK key deleted for tenant={tenant_id}, provider={provider}")
    return {"deleted": True, "provider": provider}


@router.get(
    "/keys",
    summary="List registered BYOK providers",
    response_description="List of providers with registered keys",
)
async def list_keys(request: Request):
    """List all providers that have registered BYOK API keys for this tenant.

    Returns only the provider names — never exposes the actual key values.
    """
    tenant_id = request.state.tenant_id
    keydb = get_keydb()

    # Scan for all provider keys for this tenant
    providers = []
    cursor = b"0"
    while True:
        cursor, keys = await keydb.scan(
            cursor=cursor,
            match=f"tenant:{tenant_id}:api_key:*",
            count=100,
        )
        for key in keys:
            # Extract provider name from key pattern: tenant:{tid}:api_key:{provider}
            parts = key.decode().split(":")
            if len(parts) >= 4:
                provider = parts[3]
                if provider not in providers:
                    providers.append(provider)
        if cursor == b"0":
            break

    # Check if default key exists
    has_default = await keydb.exists(f"tenant:{tenant_id}:api_key")

    return {"providers": providers, "has_default_key": bool(has_default)}
