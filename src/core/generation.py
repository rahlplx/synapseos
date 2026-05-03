"""
L3 — Generation Engine
SynapseOS uses its OWN LLM routing — NOT z.ai API.
z.ai web app is Rahul's coding tool. SynapseOS runtime: Groq → OpenRouter → Anthropic.
Tenants bring their own keys (BYOK).
"""
import os
import json
from litellm import acompletion

# Platform default chain (no z.ai API dependency)
# Tenants override this entirely via BYOK
GENERATION_MODEL = "groq/llama-3.1-70b-versatile"    # Groq free tier primary
FAST_MODEL = "groq/llama-3.1-8b-instant"              # Fast/cheap for classify + reflect


async def generate(question: str, contexts: list[str], tenant_api_key: str = None) -> str:
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_key=tenant_api_key or os.environ.get("GROQ_API_KEY"),
        messages=[
            {"role": "system", "content": "Answer precisely using only the provided context. If context lacks the answer, say so explicitly."},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        fallbacks=[
            {"model": "openrouter/meta-llama/llama-3.1-8b-instruct", "api_key": os.environ.get("OPENROUTER_API_KEY")},
            {"model": "anthropic/claude-haiku-4-5", "api_key": os.environ.get("ANTHROPIC_API_KEY")},
        ],
        num_retries=1,
        request_timeout=30,
    )
    return response.choices[0].message.content


async def generate_stream(question: str, contexts: list[str], tenant_api_key: str = None):
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_key=tenant_api_key or os.environ.get("GROQ_API_KEY"),
        messages=[
            {"role": "system", "content": "Answer precisely using only the provided context."},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        stream=True,
        fallbacks=[{"model": "openrouter/meta-llama/llama-3.1-8b-instruct"}],
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield f"data: {json.dumps({'chunk': delta})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


async def generate_hyde(query: str) -> str:
    """HyDE — uses fast Groq model, near-zero cost."""
    response = await acompletion(
        model=FAST_MODEL,
        api_key=os.environ.get("GROQ_API_KEY"),
        messages=[{"role": "user", "content": f"Write a detailed document that answers this question. Be specific.\n\nQuestion: {query}\n\nDocument:"}],
        max_tokens=300,
    )
    return f"{query}\n\n{response.choices[0].message.content}"


async def fast_complete(prompt: str, max_tokens: int = 300, json_mode: bool = False) -> str:
    """Fast cheap completion for classify/reflect — Groq Llama-8b."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = await acompletion(
        model=FAST_MODEL,
        api_key=os.environ.get("GROQ_API_KEY"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,
        **kwargs,
    )
    return response.choices[0].message.content
