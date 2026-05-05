"""
L3 — Generation Engine (Extended)
Adds generate_with_tools() for LiteLLM function calling with parallel tool execution.
Groq 70b supports function calling — used for tool path in cognitive engine.
"""
import json
import asyncio
import logging
from litellm import acompletion

from src.core.config import GENERATION_MODEL, SYSTEM_PROMPT_TOOLS, GROQ_API_KEY

logger = logging.getLogger(__name__)


async def generate_with_tools(
    question: str,
    context: str,
    available_tools: list[dict],
    tenant_api_key: str = None,
    tenant_id: str = "",
) -> tuple[str, list[str]]:
    """Generate answer with LiteLLM function calling support.

    1. Call Groq 70b with tool schemas
    2. If tool_calls: execute ALL in parallel with asyncio.gather
    3. Append tool results to messages
    4. Call LLM again to synthesize final answer

    Returns: (final_answer_text, list_of_tool_names_used)
    """
    from src.cognitive.tools import ToolExecutor

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_TOOLS},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]

    # First LLM call — may request tool usage
    response = await acompletion(
        model=GENERATION_MODEL,
        api_key=tenant_api_key or GROQ_API_KEY,
        messages=messages,
        tools=available_tools,
        tool_choice="auto",
        request_timeout=30,
    )

    tool_calls = response.choices[0].message.tool_calls or []
    tools_used = []

    if tool_calls:
        # Execute all tool calls in PARALLEL
        executor = ToolExecutor()
        tasks = []
        for tc in tool_calls:
            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                logger.warning(f"[non-critical] Tool arguments parse failed: {type(e).__name__}: {e}")
                tool_input = {}
            tasks.append(executor.execute(tc.function.name, tool_input, tenant_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Append assistant message with tool calls + tool results
        messages.append(response.choices[0].message)
        tools_used = [tc.function.name for tc in tool_calls]

        for tc, result in zip(tool_calls, results):
            result_str = str(result) if not isinstance(result, Exception) else f"Error: {result}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

        # Second LLM call — synthesize answer from tool results
        response = await acompletion(
            model=GENERATION_MODEL,
            api_key=tenant_api_key or GROQ_API_KEY,
            messages=messages,
            request_timeout=30,
        )

    return response.choices[0].message.content, tools_used
