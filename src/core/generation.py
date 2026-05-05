"""
L3 — Generation Engine
SynapseOS uses its OWN LLM routing — Groq primary → OpenRouter → Anthropic fallback.
Tenants bring their own keys (BYOK). No z.ai API dependency in runtime.
"""
import os
import json
from litellm import acompletion

from src.core.config import (
    GENERATION_MODEL, FAST_MODEL, GROQ_API_KEY,
    OPENROUTER_API_KEY, ANTHROPIC_API_KEY,
    SYSTEM_PROMPT, SYSTEM_PROMPT_STREAM,
)


async def generate(
    question: str,
    contexts: list[str],
    tenant_api_key: str = None,
) -> str:
    """Non-streaming generation with fallback chain.
    Groq 70b → OpenRouter Llama → Anthropic Haiku.
    """
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_key=tenant_api_key or GROQ_API_KEY,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        fallbacks=[
            {"model": "openrouter/meta-llama/llama-3.1-8b-instruct",
             "api_key": OPENROUTER_API_KEY},
            {"model": "anthropic/claude-haiku-4-5",
             "api_key": ANTHROPIC_API_KEY},
        ],
        num_retries=1,
        request_timeout=30,
    )
    return response.choices[0].message.content


async def generate_stream(
    question: str,
    contexts: list[str],
    tenant_api_key: str = None,
    sources: list[dict] = None,
):
    """Streaming generation with SSE format: data: {"chunk": "..."}\\n\\n
    Final message is sent by the caller (query.py) with metadata.
    """
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_key=tenant_api_key or GROQ_API_KEY,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_STREAM},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        stream=True,
        fallbacks=[
            {"model": "openrouter/meta-llama/llama-3.1-8b-instruct",
             "api_key": OPENROUTER_API_KEY},
        ],
        num_retries=1,
        request_timeout=30,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield f"data: {json.dumps({'chunk': delta})}\n\n"


async def generate_hyde(query: str) -> str:
    """HyDE — Hypothetical Document Embedding.
    Uses fast Groq 8b model, adds ~800-1200ms latency.
    """
    response = await acompletion(
        model=FAST_MODEL,
        api_key=GROQ_API_KEY,
        messages=[{
            "role": "user",
            "content": (
                f"Write a detailed document that answers this question. Be specific.\n\n"
                f"Question: {query}\n\nDocument:"
            ),
        }],
        max_tokens=300,
    )
    return f"{query}\n\n{response.choices[0].message.content}"


async def fast_complete(
    prompt: str,
    max_tokens: int = 300,
    json_mode: bool = False,
) -> str:
    """Fast cheap completion for classify/reflect — Groq Llama-8b-instant.
    ~100ms on Groq free tier.
    """
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await acompletion(
        model=FAST_MODEL,
        api_key=GROQ_API_KEY,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,
        **kwargs,
    )
    return response.choices[0].message.content
