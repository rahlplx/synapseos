"""
L7 — Tool Registry + Executor
4 built-in tools + tenant-defined custom tools (any HTTP endpoint).
ARM safe: web_search capped at 3000 chars, calculate uses safe eval, call_api has 15s timeout.
"""
import asyncio
import json
import logging
import httpx
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

from src.core.clients import get_cipher

logger = logging.getLogger(__name__)

# ─── Built-in Tool Schemas (OpenAI function calling format) ──────────────────
BUILTIN_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "Search the tenant knowledge base for relevant information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
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
            "description": "Search the live web for current information not in the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Web search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression safely. Supports +, -, *, /, parentheses.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Math expression"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_api",
            "description": "Call a registered tenant API endpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Name of the registered tool"},
                    "payload": {"type": "object", "description": "JSON payload"},
                },
                "required": ["tool_name"],
            },
        },
    },
]

CALC_ALLOWED_CHARS = set("0123456789+-*/()., ")


class ToolExecutor:
    """Executes built-in and tenant-defined tools. Never crashes — returns error string on failure."""

    async def execute(self, tool_name: str, tool_input: dict, tenant_id: str) -> str:
        """Execute a tool by name."""
        try:
            if tool_name == "retrieve_knowledge":
                return await self._retrieve_knowledge(tool_input, tenant_id)
            elif tool_name == "web_search":
                return await self._web_search(tool_input)
            elif tool_name == "calculate":
                return self._calculate(tool_input)
            elif tool_name == "call_api":
                return await self._call_api(tool_input, tenant_id)
            return f"Error: unknown tool '{tool_name}'"
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)[:200]}"

    async def _retrieve_knowledge(self, tool_input: dict, tenant_id: str) -> str:
        """Search the tenant knowledge base using hybrid retrieval."""
        from src.core.retrieval import hybrid_query
        top_k = min(tool_input.get("top_k", 5), 20)
        hits = await hybrid_query(tool_input["query"], tenant_id, final_k=top_k)
        if not hits:
            return "No relevant documents found in knowledge base."
        return "\n\n".join(h.payload.get("text", "") for h in hits)

    async def _web_search(self, tool_input: dict) -> str:
        """Search the web using Crawl4AI. Output capped at 3000 chars."""
        from urllib.parse import quote_plus
        query = tool_input["query"]
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=f"https://search.brave.com/search?q={quote_plus(query)}",
                config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=15000),
            )
            text = result.markdown.fit_markdown if result.markdown else ""
            return text[:3000] if text else "No web search results found."

    def _calculate(self, tool_input: dict) -> str:
        """Safely evaluate a mathematical expression. Only allows 0-9 and basic operators."""
        expr = tool_input.get("expression", "")
        if not all(c in CALC_ALLOWED_CHARS for c in expr):
            return "Error: unsafe expression — only numbers and basic operators allowed"
        try:
            return str(eval(expr))  # noqa: S307 — input is sanitized above
        except ZeroDivisionError:
            return "Error: division by zero"
        except Exception as e:
            return f"Error: {str(e)[:100]}"

    async def _call_api(self, tool_input: dict, tenant_id: str) -> str:
        """Call a tenant-registered custom API tool. 15s timeout. Output capped at 3000 chars."""
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

        headers = {}
        if tool["auth_header"]:
            try:
                auth = get_cipher().decrypt(tool["auth_header"]).decode()
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
