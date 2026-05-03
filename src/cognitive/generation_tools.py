"""
L3 — Generation Engine (Extended)
Adds generate_with_tools() for LiteLLM function calling with parallel tool execution.
Groq 70b supports function calling — used for tool path in cognitive engine.
"""
import os
import json
import asyncio
from litellm import acompletion

# ─── Model Constants ──────────────────────────────────────────────────────────
GENERATION_MODEL = "groq/llama-3.1-70b-versatile"    # Primary: quality + tool calling
FAST_MODEL = "groq/llama-3.1-8b-instant"              # Fast: classify + reflect

SYSTEM_PROMPT = (
    "You are a precise knowledge assistant. Answer ONLY from the provided context. "
    "If the context does not contain the answer, say so explicitly."
)

SYSTEM_PROMPT_TOOLS = (
    "You are a precise assistant with access to tools. "
    "Use tools when needed to find information. "
    "Base your final answer on retrieved context and tool results."
)


async def generate_with_tools(
    question: str,
    context: str,
    available_tools: list[dict],
    tenant_api_key: str = None,
) -> tuple[str, list[str]]:
    """Generate answer with LiteLLM function calling support.

    1. Call Groq 70b with tool schemas (supports function calling)
    2. If tool_calls in response: execute ALL in parallel with asyncio.gather
    3. Append tool results to messages
    4. Call LLM again to synthesize final answer using tool results

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
        api_key=tenant_api_key or os.environ.get("GROQ_API_KEY"),
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
        # We need tenant_id — extract from context or use empty string
        # In practice, tenant_id is passed through the cognitive engine
        tasks = []
        for tc in tool_calls:
            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_input = {}
            tasks.append(executor.execute(tc.function.name, tool_input, ""))

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
            api_key=tenant_api_key or os.environ.get("GROQ_API_KEY"),
            messages=messages,
            request_timeout=30,
        )

    return response.choices[0].message.content, tools_used
