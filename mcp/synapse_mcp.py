"""
SynapseOS MCP Server (FastMCP)
Install: fastmcp install claude mcp/synapse_mcp.py
Cursor:  add to .cursor/mcp.json
"""
import os
import httpx
from fastmcp import FastMCP
from synapseos import AsyncSynapseClient

mcp = FastMCP(
    "SynapseOS",
    instructions=(
        "Query organizational knowledge. Use query_knowledge for facts, "
        "think for complex reasoning with memory, ingest_url to learn new documents, "
        "check_job_status to poll ingestion progress, get_stats for knowledge base stats."
    ),
)

client = AsyncSynapseClient(
    base_url=os.environ.get("SYNAPSE_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("SYNAPSE_API_KEY", ""),
    tenant_id=os.environ.get("SYNAPSE_TENANT_ID", "default"),
)


@mcp.tool()
async def query_knowledge(question: str) -> str:
    """Query the knowledge base. Use for any factual question about organizational documents, policies, or content."""
    result = await client.query(question)
    sources = "\n".join(
        f"- {s.get('source_url', 'internal')}" for s in result.sources if s
    )
    return f"{result.answer}\n\nSources:\n{sources}" if sources else result.answer


@mcp.tool()
async def think(question: str, session_id: str = "mcp-session", user_id: str = "mcp-user") -> str:
    """Full cognitive query with memory and reasoning. Use for complex multi-step questions that require thinking, comparing, or synthesis."""
    result = await client.think(question, session_id, user_id)
    tools_str = ", ".join(result.tools_used) if result.tools_used else "none"
    return (
        f"{result.answer}\n\n"
        f"---\n"
        f"Query type: {result.query_type} | Steps: {result.steps_taken} | "
        f"Memories recalled: {result.memories_recalled} | Tools used: {tools_str}"
    )


@mcp.tool()
async def ingest_url(url: str) -> str:
    """Ingest a URL into the knowledge base. Use when asked to 'learn', 'index', or 'remember' a document."""
    job = await client.ingest(urls=[url])
    return f"Ingestion queued. Job ID: {job.job_id}"


@mcp.tool()
async def submit_feedback(trace_id: str, positive: bool) -> str:
    """Submit thumbs up/down on a response. positive=True for thumbs up, False for thumbs down."""
    await client.feedback(trace_id, 1 if positive else -1)
    return "Feedback recorded."


@mcp.tool()
async def check_job_status(job_id: str) -> str:
    """Check if an ingestion job is done, processing, or failed. Returns human-readable status."""
    try:
        status = await client.job_status(job_id)
        state = status.get("status", "unknown")
        if state == "done":
            chunks = status.get("chunk_count", "?")
            return f"Status: done | Chunks stored: {chunks}"
        elif state == "processing":
            current = status.get("current_url", "")
            done = status.get("done", 0)
            total = status.get("total", "?")
            return f"Status: processing ({done}/{total}) | Current: {current}"
        elif state == "failed":
            error = status.get("error", "unknown error")
            return f"Status: failed | Error: {error}"
        return f"Status: {state}"
    except Exception as e:
        return f"Error checking job: {e}"


@mcp.tool()
async def get_stats() -> str:
    """Get knowledge base statistics for the current tenant. Shows vector count and document count."""
    try:
        data = await client.collections()
        vectors = data.get("vector_count", 0)
        tenant = data.get("tenant_id", "unknown")
        status = data.get("status", "unknown")
        return f"Knowledge base: {vectors:,} vectors | Tenant: {tenant} | Status: {status}"
    except Exception as e:
        return f"Error fetching stats: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
