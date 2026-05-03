"""
L3 — Generation Engine
z.ai GLM models via LiteLLM. Fallback: Groq → OpenRouter → Anthropic.
z.ai glm-4.7-flash is FREE — used for HyDE, classification, reflection.
"""
import os
import json
from litellm import acompletion

# z.ai is the primary provider (OpenAI-compatible)
ZAI_BASE = "https://api.z.ai/api/paas/v4/"
ZAI_KEY = os.environ.get("ZAI_API_KEY", "")

GENERATION_MODEL = "openai/glm-5.1"       # paid flagship — use tenant BYOK
FAST_MODEL = "openai/glm-5.1"       # FREE — classification, reflection, HyDE


async def generate(question: str, contexts: list[str], tenant_api_key: str = None) -> str:
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_base=ZAI_BASE,
        api_key=tenant_api_key or ZAI_KEY,
        messages=[
            {"role": "system", "content": "Answer precisely using only the provided context. If context lacks the answer, say so."},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        fallbacks=[
            {"model": "groq/llama-3.1-8b-instant"},
            {"model": "openrouter/meta-llama/llama-3.1-8b-instruct"},
            {"model": "anthropic/claude-haiku-4-5"},
        ],
        num_retries=1,
        request_timeout=30,
    )
    return response.choices[0].message.content


async def generate_stream(question: str, contexts: list[str], tenant_api_key: str = None):
    context_str = "\n\n---\n\n".join(contexts)
    response = await acompletion(
        model=GENERATION_MODEL,
        api_base=ZAI_BASE,
        api_key=tenant_api_key or ZAI_KEY,
        messages=[
            {"role": "system", "content": "Answer precisely using only the provided context."},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"},
        ],
        stream=True,
        fallbacks=[{"model": "groq/llama-3.1-8b-instant"}],
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield f"data: {json.dumps({'chunk': delta})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


async def generate_hyde(query: str) -> str:
    """Hypothetical Document Embedding — uses FREE z.ai flash model."""
    response = await acompletion(
        model=FAST_MODEL,
        api_base=ZAI_BASE,
        api_key=ZAI_KEY,
        messages=[{
            "role": "user",
            "content": f"Write a detailed document that would perfectly answer this question. Be specific and factual.\n\nQuestion: {query}\n\nDocument:",
        }],
        max_tokens=300,
    )
    return f"{query}\n\n{response.choices[0].message.content}"


async def fast_complete(prompt: str, max_tokens: int = 300, json_mode: bool = False) -> str:
    """Fast FREE z.ai flash completion — for classification, reflection, mem0 judge."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = await acompletion(
        model=FAST_MODEL,
        api_base=ZAI_BASE,
        api_key=ZAI_KEY,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,
        **kwargs,
    )
    return response.choices[0].message.content
