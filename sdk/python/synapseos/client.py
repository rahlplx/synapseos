"""SynapseOS Python SDK — AsyncSynapseClient"""
import json
import httpx
from dataclasses import dataclass


@dataclass
class QueryResult:
    answer: str
    sources: list
    trace_id: str = ""
    latency_ms: int = 0


@dataclass
class IngestJob:
    job_id: str
    status: str


class AsyncSynapseClient:
    def __init__(self, base_url: str, api_key: str, tenant_id: str):
        self._base = base_url.rstrip("/") + "/v1"
        self._headers = {"Authorization": f"Bearer {api_key}", "X-Tenant-ID": tenant_id, "Content-Type": "application/json"}

    async def query(self, question: str, top_k: int = 5) -> QueryResult:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(f"{self._base}/query", headers=self._headers,
                json={"question": question, "top_k": top_k, "stream": False})
            resp.raise_for_status()
            data = resp.json()
            return QueryResult(answer=data["answer"], sources=data.get("sources", []))

    async def query_stream(self, question: str, top_k: int = 5):
        async with httpx.AsyncClient(timeout=120) as http:
            async with http.stream("POST", f"{self._base}/query", headers=self._headers,
                    json={"question": question, "top_k": top_k, "stream": True}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        payload = json.loads(line[6:])
                        if "chunk" in payload:
                            yield payload["chunk"]
                        if payload.get("done"):
                            break

    async def think(self, question: str, session_id: str, user_id: str) -> dict:
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(f"{self._base}/think", headers=self._headers,
                json={"question": question, "session_id": session_id, "user_id": user_id, "stream": False})
            resp.raise_for_status()
            return resp.json()

    async def ingest(self, urls: list[str], metadata: dict = None) -> IngestJob:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(f"{self._base}/ingest", headers=self._headers,
                json={"urls": urls, "metadata": metadata or {}})
            resp.raise_for_status()
            data = resp.json()
            return IngestJob(job_id=data["job_id"], status=data["status"])

    async def feedback(self, trace_id: str, rating: int):
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(f"{self._base}/feedback", headers=self._headers,
                json={"trace_id": trace_id, "rating": rating})
