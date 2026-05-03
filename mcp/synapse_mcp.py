"""
SynapseOS MCP Server (FastMCP)
Install: fastmcp install claude mcp/synapse_mcp.py
Cursor:  add to .cursor/mcp.json
"""
import os
from fastmcp import FastMCP
from synapseos import AsyncSynapseClient

mcp = FastMCP("SynapseOS", instructions="Query organizational knowledge. Use query_knowledge for facts, ingest_url to learn new documents.")
client = AsyncSynapseClient(
    base_url=os.environ.get("SYNAPSE_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("SYNAPSE_API_KEY", ""),
    tenant_id=os.environ.get("SYNAPSE_TENANT_ID", "default"),
)

@mcp.tool()
async def query_knowledge(question: str) -> str:
    """Query the knowledge base. Use for any factual question about organizational documents, policies, or content."""
    result = await client.query(question)
    return result.answer

@mcp.tool()
async def think(question: str, session_id: str, user_id: str = "mcp-user") -> str:
    """Full cognitive query with memory and reasoning. Use for complex multi-step questions."""
    result = await client.think(question, session_id, user_id)
    return result["answer"]

@mcp.tool()
async def ingest_url(url: str) -> str:
    """Ingest a URL into the knowledge base. Use when asked to 'learn', 'index', or 'remember' a document."""
    job = await client.ingest(urls=[url])
    return f"Queued. Job ID: {job.job_id}"

@mcp.tool()
async def submit_feedback(trace_id: str, positive: bool) -> str:
    """Submit thumbs up/down on a response."""
    await client.feedback(trace_id, 1 if positive else -1)
    return "Feedback recorded."

if __name__ == "__main__":
    mcp.run(transport="stdio")
