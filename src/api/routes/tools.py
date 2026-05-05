"""POST /v1/tools, GET /v1/tools, DELETE /v1/tools/{name} — Custom tool management.

Tenants can register HTTP endpoints as tools that the cognitive engine can invoke
via `call_api`. Tool auth headers are encrypted at rest with Fernet.
The tools table is also used by the ToolExecutor._call_api() method.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException

from src.api.models import RegisterToolRequest, ErrorResponse
from src.core.clients import get_cipher
from src.core.db import get_pool

router = APIRouter(tags=["tools"])
logger = logging.getLogger(__name__)


@router.post(
    "/tools",
    summary="Register custom tool",
    response_description="Confirmation of tool registration",
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def register_tool(body: RegisterToolRequest, request: Request):
    """Register a custom HTTP tool for this tenant.

    The tool is stored in the PostgreSQL `tools` table. The auth header
    (if provided) is encrypted with Fernet before storage. When the cognitive
    engine calls `call_api`, it decrypts the auth header and attaches it
    to the outbound request.

    Tool names must be unique per tenant. To update an existing tool,
    delete it first and re-register.
    """
    tenant_id = request.state.tenant_id
    pool = await get_pool()

    # Validate method
    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
    if body.method.upper() not in valid_methods:
        raise HTTPException(400, f"Invalid HTTP method '{body.method}'. Must be one of: {', '.join(sorted(valid_methods))}")

    # Check for name conflict
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT name FROM tools WHERE tenant_id=$1 AND name=$2",
            tenant_id, body.name,
        )
        if existing:
            raise HTTPException(409, f"Tool '{body.name}' already exists for this tenant. Delete it first to update.")

    # Encrypt auth header if provided
    encrypted_auth = None
    if body.auth_header:
        try:
            cipher = get_cipher()
            encrypted_auth = cipher.encrypt(body.auth_header.encode()).decode()
        except RuntimeError as e:
            raise HTTPException(400, f"Cannot encrypt auth header: {e}")

    # Insert
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tools (tenant_id, name, endpoint_url, method, auth_header, description, active, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            tenant_id, body.name, body.endpoint_url, body.method.upper(),
            encrypted_auth, body.description, body.active, datetime.now(timezone.utc),
        )

    logger.info(f"[tools] Tool registered: tenant={tenant_id}, name={body.name}, method={body.method.upper()}")
    return {"registered": True, "name": body.name, "method": body.method.upper()}


@router.get(
    "/tools",
    summary="List custom tools",
    response_description="List of registered tools for this tenant",
)
async def list_tools(request: Request):
    """List all custom tools registered by this tenant.

    Returns tool metadata but never exposes the auth header values.
    Use pagination with `limit` and `offset` parameters.
    """
    tenant_id = request.state.tenant_id
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT name, endpoint_url, method, description, active, created_at
            FROM tools WHERE tenant_id=$1
            ORDER BY created_at DESC
            """,
            tenant_id,
        )

    tools = [
        {
            "name": r["name"],
            "endpoint_url": r["endpoint_url"],
            "method": r["method"],
            "description": r["description"],
            "active": r["active"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"tools": tools, "count": len(tools)}


@router.get(
    "/tools/{name}",
    summary="Get tool details",
    response_description="Tool configuration (auth header redacted)",
    responses={404: {"model": ErrorResponse}},
)
async def get_tool(name: str, request: Request):
    """Get details for a specific custom tool. Auth header is never exposed."""
    tenant_id = request.state.tenant_id
    pool = await get_pool()

    async with pool.acquire() as conn:
        tool = await conn.fetchrow(
            """
            SELECT name, endpoint_url, method, description, active, has_auth_header, created_at
            FROM (
                SELECT *, (auth_header IS NOT NULL) as has_auth_header
                FROM tools
            ) sub
            WHERE tenant_id=$1 AND name=$2
            """,
            tenant_id, name,
        )

    if not tool:
        raise HTTPException(404, f"Tool '{name}' not found")

    return {
        "name": tool["name"],
        "endpoint_url": tool["endpoint_url"],
        "method": tool["method"],
        "description": tool["description"],
        "active": tool["active"],
        "has_auth_header": tool["has_auth_header"],
        "created_at": tool["created_at"].isoformat() if tool["created_at"] else None,
    }


@router.delete(
    "/tools/{name}",
    summary="Delete custom tool",
    response_description="Confirmation of tool deletion",
    responses={404: {"model": ErrorResponse}},
)
async def delete_tool(name: str, request: Request):
    """Delete a custom tool by name. The tool will no longer be callable."""
    tenant_id = request.state.tenant_id
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM tools WHERE tenant_id=$1 AND name=$2",
            tenant_id, name,
        )

    deleted = result.endswith("1")  # "DELETE 1" → True
    if not deleted:
        raise HTTPException(404, f"Tool '{name}' not found")

    logger.info(f"[tools] Tool deleted: tenant={tenant_id}, name={name}")
    return {"deleted": True, "name": name}
