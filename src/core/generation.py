"""
L3 — Generation Engine
SynapseOS uses its OWN LLM routing — Groq primary → OpenRouter → Anthropic fallback.
Tenants bring their own keys (BYOK). No z.ai API dependency in runtime.
"""
import os
import json
from litellm import acompletion

# ─── Model Constants ──────────────────────────────────────────────────────────
GENERATION_MODEL = "groq/llama-3.1-70b-versatile"    # Primary: quality generation
FAST_MODEL = "groq/llama-3.1-8b-instant"              # Fast: classify + reflect + mem0 judge

SYSTEM_PROMPT = (
    "You are a precise knowledge assistant. Answer ONLY from the provided context. "
    "If the context does not contain the answer, say so explicitly."
)

SYSTEM_PROMPT_STREAM = (
    "You are a precise knowledge assistant. Answer using only the provided context."
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
        api_key=tenant_api_key or os.environ.get("GROQ_API_KEY"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        fallbacks=[
            {"model": "openrouter/meta-llama/llama-3.1-8b-instruct",
             "api_key": os.environ.get("OPENROUTER_API_KEY")},
            {"model": "anthropic/claude-haiku-4-5",
             "api_key": os.environ.get("ANTHROPIC_API_KEY")},
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
    Final message: data: {"done": true, "sources": [...]}\n\n
    """
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_key=tenant_api_key or os.environ.get("GROQ_API_KEY"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_STREAM},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        stream=True,
        fallbacks=[
            {"model": "openrouter/meta-llama/llama-3.1-8b-instruct",
             "api_key": os.environ.get("OPENROUTER_API_KEY")},
        ],
        num_retries=1,
        request_timeout=30,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield f"data: {json.dumps({'chunk': delta})}\n\n"

    # NOTE: No final "done" message emitted here — the caller (query.py)
    # is responsible for sending the final SSE message with metadata
    # (trace_id, sources, reflection_scores, etc.). If we emit a done
    # message here, the client receives TWO done events.


async def generate_hyde(query: str) -> str:
    """HyDE — Hypothetical Document Embedding.
    Uses fast Groq 8b model, adds ~800-1200ms latency.
    Default OFF for latency-sensitive paths.
    """
    response = await acompletion(
        model=FAST_MODEL,
        api_key=os.environ.get("GROQ_API_KEY"),
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
    ~100ms on Groq free tier. Used by cognitive engine components.
    """
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await acompletion(
        model=FAST_MODEL,
        api_key=os.environ.get("GROQ_API_KEY"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,
        **kwargs,
    )
    return response.choices[0].message.content
