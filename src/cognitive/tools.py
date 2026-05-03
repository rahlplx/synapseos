"""
L7 — Tool Registry + Executor
4 built-in tools + tenant-defined custom tools (any HTTP endpoint).
"""
import os, json
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
import httpx

BUILTIN_SCHEMAS = [
    {"type": "function", "function": {"name": "retrieve_knowledge", "description": "Search the tenant knowledge base.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "web_search", "description": "Search the live web for current info.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "calculate", "description": "Evaluate a math expression.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
    {"type": "function", "function": {"name": "call_api", "description": "Call a registered tenant API.", "parameters": {"type": "object", "properties": {"tool_name": {"type": "string"}, "payload": {"type": "object"}}, "required": ["tool_name"]}}},
]


class ToolExecutor:
    async def execute(self, tool_name: str, tool_input: dict, tenant_id: str) -> str:
        if tool_name == "retrieve_knowledge":
            from src.core.retrieval import hybrid_query
            hits = await hybrid_query(tool_input["query"], tenant_id, final_k=5)
            return "\n\n".join(h.payload["text"] for h in hits)

        elif tool_name == "web_search":
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(
                    url=f"https://search.brave.com/search?q={tool_input['query']}",
                    config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=15000),
                )
                return result.markdown.fit_markdown[:3000]

        elif tool_name == "calculate":
            expr = tool_input["expression"]
            allowed = set("0123456789+-*/()., ")
            if not all(c in allowed for c in expr):
                return "Error: unsafe expression"
            try:
                return str(eval(expr))  # noqa: S307
            except Exception as e:
                return f"Error: {e}"

        elif tool_name == "call_api":
            # TODO: load tenant tool from DB, decrypt auth, execute
            return "Custom API tool execution — implement in Phase 3"

        return "Unknown tool"
