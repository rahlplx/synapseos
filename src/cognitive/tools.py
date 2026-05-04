"""
L7 — Tool Registry + Executor
4 built-in tools + tenant-defined custom tools (any HTTP endpoint).
ARM safe: web_search capped at 3000 chars, calculate uses safe eval, call_api has 15s timeout.
"""
import os
import json
import logging
import httpx
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# ─── Built-in Tool Schemas (OpenAI function calling format) ──────────────────
BUILTIN_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "Search the tenant knowledge base for relevant information. Use this when you need factual information from the organization's documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for knowledge base"},
                    "top_k": {"type": "integer", "description": "Number of results", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live web for current information not in the knowledge base. Use when you need up-to-date info or external data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression safely. Supports +, -, *, /, parentheses, and decimals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_api",
            "description": "Call a registered tenant API endpoint. Use when you need to interact with external services or databases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Name of the registered tool"},
                    "payload": {"type": "object", "description": "JSON payload to send"},
                },
                "required": ["tool_name"],
            },
        },
    },
]

# Allowed characters for calculate tool — strict safety
CALC_ALLOWED_CHARS = set("0123456789+-*/()., ")


class ToolExecutor:
    """Executes built-in and tenant-defined tools.
    All methods return strings (never crash, always return error message on failure).
    """

    async def execute(self, tool_name: str, tool_input: dict, tenant_id: str) -> str:
        """Execute a tool by name. Returns result as string."""
        try:
            if tool_name == "retrieve_knowledge":
                return await self._retrieve_knowledge(tool_input, tenant_id)
            elif tool_name == "web_search":
                return await self._web_search(tool_input)
            elif tool_name == "calculate":
                return self._calculate(tool_input)
            elif tool_name == "call_api":
                return await self._call_api(tool_input, tenant_id)
            else:
                return f"Error: unknown tool '{tool_name}'"
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)[:200]}"

    async def _retrieve_knowledge(self, tool_input: dict, tenant_id: str) -> str:
        """Search the tenant knowledge base using hybrid retrieval."""
        from src.core.retrieval import hybrid_query
        top_k = tool_input.get("top_k", 5)
        hits = await hybrid_query(tool_input["query"], tenant_id, final_k=top_k)
        if not hits:
            return "No relevant documents found in knowledge base."
        return "\n\n".join(h.payload.get("text", "") for h in hits)

    async def _web_search(self, tool_input: dict) -> str:
        """Search the web using Crawl4AI.
        ARM: page_timeout=15000, output capped at 3000 chars.
        """
        query = tool_input["query"]
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=f"https://search.brave.com/search?q={query}",
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    page_timeout=15000,
                ),
            )
            text = result.markdown.fit_markdown if result.markdown else ""
            return text[:3000] if text else "No web search results found."

    def _calculate(self, tool_input: dict) -> str:
        """Safely evaluate a mathematical expression.
        ONLY allows: 0-9, +, -, *, /, (, ), ., comma, space.
        Rejects anything else (prevents code injection).
        """
        expr = tool_input.get("expression", "")
        if not all(c in CALC_ALLOWED_CHARS for c in expr):
            return "Error: unsafe expression — only numbers and basic operators allowed"
        try:
            result = eval(expr)  # noqa: S307 — input is sanitized above
            return str(result)
        except ZeroDivisionError:
            return "Error: division by zero"
        except Exception as e:
            return f"Error: {str(e)[:100]}"

    async def _call_api(self, tool_input: dict, tenant_id: str) -> str:
        """Call a tenant-registered custom API tool.
        Auth header is Fernet-decrypted from PostgreSQL. 15s timeout.
        Output capped at 3000 chars.
        """
        from src.core.db import get_pool
        tool_name = tool_input.get("tool_name", "")
        payload = tool_input.get("payload", {})

        pool = await get_pool()
        async with pool.acquire() as conn:
            tool = await conn.fetchrow(
                "SELECT * FROM tools WHERE tenant_id=$1 AND name=$2 AND active=TRUE",
                tenant_id, tool_name,
            )

        if not tool:
            return f"Error: tool '{tool_name}' not found for tenant {tenant_id}"

        # Decrypt auth header if present
        headers = {}
        if tool["auth_header"]:
            try:
                cipher = Fernet(os.environ["ENCRYPTION_KEY"].encode())
                auth = cipher.decrypt(tool["auth_header"]).decode()
                headers["Authorization"] = auth
            except Exception as e:
                logger.warning(f"[security] Fernet decrypt failed for tool '{tool_name}': {type(e).__name__}")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                method=tool["method"] or "GET",
                url=tool["endpoint_url"],
                json=payload,
                headers=headers,
            )
            return resp.text[:3000]
