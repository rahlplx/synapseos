"""SynapseOS Python SDK — AsyncSynapseClient
Full async client for SynapseOS RAG platform.
Install: pip install synapseos
"""
import json
import httpx
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


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


class AsyncSynapseClient:
    """Async Python client for SynapseOS API.

    Usage:
        client = AsyncSynapseClient(
            base_url="https://api.synapseos.com",
            api_key="sk-syn-...",
            tenant_id="org-xyz",
        )
        result = await client.query("What is our refund policy?")
    """

    def __init__(self, base_url: str, api_key: str, tenant_id: str):
        self._base = base_url.rstrip("/") + "/v1"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Tenant-ID": tenant_id,
            "Content-Type": "application/json",
        }

    async def query(
        self,
        question: str,
        top_k: int = 5,
        use_hyde: bool = False,
    ) -> QueryResult:
        """Non-streaming RAG query. Returns full answer with sources."""
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{self._base}/query",
                headers=self._headers,
                json={
                    "question": question,
                    "top_k": top_k,
                    "stream": False,
                    "use_hyde": use_hyde,
                },
            )
            resp.raise_for_status()
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
        """Streaming RAG query. Yields answer chunks in real-time via SSE."""
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
        """Full cognitive query with memory + reasoning + tools + reflection."""
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(
                f"{self._base}/think",
                headers=self._headers,
                json={
                    "question": question,
                    "session_id": session_id,
                    "user_id": user_id,
                    "stream": stream,
                },
            )
            resp.raise_for_status()
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
            resp = await http.post(
                f"{self._base}/ingest",
                headers=self._headers,
                json={"urls": urls, "metadata": metadata or {}},
            )
            resp.raise_for_status()
            data = resp.json()
            return IngestJob(job_id=data["job_id"], status=data["status"])

    async def ingest_file(
        self,
        file_path: str,
    ) -> IngestJob:
        """Upload a file for ingestion."""
        async with httpx.AsyncClient(timeout=60) as http:
            with open(file_path, "rb") as f:
                resp = await http.post(
                    f"{self._base}/ingest/file",
                    headers={
                        k: v for k, v in self._headers.items()
                        if k != "Content-Type"
                    },
                    files={"file": (file_path, f)},
                )
            resp.raise_for_status()
            data = resp.json()
            return IngestJob(job_id=data["job_id"], status=data["status"])

    async def job_status(self, job_id: str) -> dict:
        """Poll ingestion job status."""
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"{self._base}/ingest/{job_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def feedback(self, trace_id: str, rating: int):
        """Submit thumbs up (+1) or thumbs down (-1) on a response."""
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(
                f"{self._base}/feedback",
                headers=self._headers,
                json={"trace_id": trace_id, "rating": rating},
            )

    async def collections(self) -> dict:
        """Get collection stats for the tenant."""
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"{self._base}/collections",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
