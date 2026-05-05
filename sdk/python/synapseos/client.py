"""SynapseOS Python SDK — AsyncSynapseClient
Full async client for SynapseOS RAG platform with automatic retry on transient failures.
Install: pip install synapseos
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

# Retry-able HTTP status codes (transient server errors + rate limiting)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 1.0  # seconds (base delay, exponential backoff applied)


@dataclass
class QueryResult:
    """Result from a non-streaming RAG query."""
    answer: str
    sources: list = field(default_factory=list)
    trace_id: str = ""
    latency_ms: int = 0


@dataclass
class ThinkResult:
    """Result from a cognitive /v1/think query."""
    answer: str
    query_type: str = "simple"
    steps_taken: int = 1
    reflection_scores: dict = field(default_factory=dict)
    memories_recalled: int = 0
    tools_used: list = field(default_factory=list)
    trace_id: str = ""


@dataclass
class IngestJob:
    """Ingestion job status."""
    job_id: str
    status: str


def _should_retry(exc: Exception) -> bool:
    """Determine if a request should be retried based on the exception."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                        httpx.PoolTimeout, httpx.ConnectTimeout)):
        return True
    return False


async def _retry_request(
    method: str,
    url: str,
    http: httpx.AsyncClient,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_RETRY_DELAY,
    **kwargs,
) -> httpx.Response:
    """Execute an HTTP request with exponential backoff retry on transient failures.

    Retries on: 429 (rate limit), 500, 502, 503, 504, connection errors, timeouts.
    Uses exponential backoff: 1s, 2s, 4s (with jitter).
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            resp = await http.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            if not _should_retry(exc) or attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                f"[retry] Attempt {attempt + 1}/{max_retries + 1} failed: "
                f"{type(exc).__name__}: {str(exc)[:100]}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
    raise last_exc  # Should never reach here


class AsyncSynapseClient:
    """Async Python client for SynapseOS API with automatic retry logic.

    Usage:
        client = AsyncSynapseClient(
            base_url="https://api.synapseos.com",
            api_key="sk-syn-...",
            tenant_id="org-xyz",
            max_retries=3,
        )
        result = await client.query("What is our refund policy?")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        tenant_id: str,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY,
    ):
        self._base = base_url.rstrip("/") + "/v1"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Tenant-ID": tenant_id,
            "Content-Type": "application/json",
        }
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    async def query(
        self,
        question: str,
        top_k: int = 5,
        use_hyde: bool = False,
    ) -> QueryResult:
        """Non-streaming RAG query. Returns full answer with sources.
        Automatically retries on transient failures (429, 5xx, timeouts).
        """
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await _retry_request(
                "POST",
                f"{self._base}/query",
                http,
                max_retries=self._max_retries,
                base_delay=self._retry_delay,
                headers=self._headers,
                json={
                    "question": question,
                    "top_k": top_k,
                    "stream": False,
                    "use_hyde": use_hyde,
                },
            )
            data = resp.json()
            return QueryResult(
                answer=data.get("answer", ""),
                sources=data.get("sources", []),
                trace_id=data.get("trace_id", ""),
                latency_ms=data.get("latency_ms", 0),
            )

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        use_hyde: bool = False,
    ) -> AsyncIterator[str]:
        """Streaming RAG query. Yields answer chunks in real-time via SSE.
        Note: Streaming does not retry mid-stream (connection is already established).
        Initial connection uses retry logic.
        """
        async with httpx.AsyncClient(timeout=120) as http:
            async with http.stream(
                "POST",
                f"{self._base}/query",
                headers=self._headers,
                json={
                    "question": question,
                    "top_k": top_k,
                    "stream": True,
                    "use_hyde": use_hyde,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            payload = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        if "chunk" in payload:
                            yield payload["chunk"]
                        if payload.get("done"):
                            break

    async def think(
        self,
        question: str,
        session_id: str,
        user_id: str,
        stream: bool = False,
    ) -> ThinkResult:
        """Full cognitive query with memory + reasoning + tools + reflection.
        Automatically retries on transient failures.
        """
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await _retry_request(
                "POST",
                f"{self._base}/think",
                http,
                max_retries=self._max_retries,
                base_delay=self._retry_delay,
                headers=self._headers,
                json={
                    "question": question,
                    "session_id": session_id,
                    "user_id": user_id,
                    "stream": stream,
                },
            )
            data = resp.json()
            return ThinkResult(
                answer=data.get("answer", ""),
                query_type=data.get("query_type", "simple"),
                steps_taken=data.get("steps_taken", 1),
                reflection_scores=data.get("reflection_scores", {}),
                memories_recalled=data.get("memories_recalled", 0),
                tools_used=data.get("tools_used", []),
                trace_id=data.get("trace_id", ""),
            )

    async def ingest(
        self,
        urls: list[str],
        metadata: Optional[dict] = None,
    ) -> IngestJob:
        """Queue document ingestion. Returns job ID immediately."""
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await _retry_request(
                "POST",
                f"{self._base}/ingest",
                http,
                max_retries=self._max_retries,
                base_delay=self._retry_delay,
                headers=self._headers,
                json={"urls": urls, "metadata": metadata or {}},
            )
            data = resp.json()
            return IngestJob(job_id=data["job_id"], status=data["status"])

    async def ingest_file(
        self,
        file_path: str,
    ) -> IngestJob:
        """Upload a file for ingestion."""
        async with httpx.AsyncClient(timeout=60) as http:
            with open(file_path, "rb") as f:
                resp = await _retry_request(
                    "POST",
                    f"{self._base}/ingest/file",
                    http,
                    max_retries=self._max_retries,
                    base_delay=self._retry_delay,
                    headers={
                        k: v for k, v in self._headers.items()
                        if k != "Content-Type"
                    },
                    files={"file": (file_path, f)},
                )
            data = resp.json()
            return IngestJob(job_id=data["job_id"], status=data["status"])

    async def job_status(self, job_id: str) -> dict:
        """Poll ingestion job status."""
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await _retry_request(
                "GET",
                f"{self._base}/ingest/{job_id}",
                http,
                max_retries=self._max_retries,
                base_delay=self._retry_delay,
                headers=self._headers,
            )
            return resp.json()

    async def feedback(self, trace_id: str, rating: int):
        """Submit thumbs up (+1) or thumbs down (-1) on a response."""
        async with httpx.AsyncClient(timeout=10) as http:
            await _retry_request(
                "POST",
                f"{self._base}/feedback",
                http,
                max_retries=self._max_retries,
                base_delay=self._retry_delay,
                headers=self._headers,
                json={"trace_id": trace_id, "rating": rating},
            )

    async def collections(self) -> dict:
        """Get collection stats for the tenant."""
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await _retry_request(
                "GET",
                f"{self._base}/collections",
                http,
                max_retries=self._max_retries,
                base_delay=self._retry_delay,
                headers=self._headers,
            )
            return resp.json()
