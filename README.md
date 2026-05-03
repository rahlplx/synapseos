# SynapseOS

Self-improving BYOK RAG platform with cognitive engine. Integrates with any app via REST API, Python SDK, TypeScript SDK, or MCP server.

## What It Does

| Endpoint | Mode | Latency |
|---|---|---|
| `POST /v1/query` | Fast hybrid RAG | ~235ms |
| `POST /v1/think` | Cognitive (memory + reasoning + tools + reflection) | ~865ms |

## Stack

Qdrant · fastembed (bge-base-en-v1.5) · z.ai GLM models · LiteLLM · Crawl4AI · Docling · RAGAS · DSPy · mem0 · Langfuse · KeyDB · MinIO · FastAPI · FastMCP · Cloudflare Workers · Coolify

## Quick Start

```bash
git clone https://github.com/rahlplx/synapseos
cd synapseos
cp .env.example .env        # fill in your API keys
docker compose up -d
./scripts/healthcheck.sh    # verify all green
```

## Integration

```python
# Python SDK
pip install synapseos
from synapseos import AsyncSynapseClient
client = AsyncSynapseClient(base_url="...", api_key="...", tenant_id="...")
result = await client.query("What is our refund policy?")
```

```typescript
// TypeScript SDK
npm install @synapseos/sdk
import { SynapseOSClient } from "@synapseos/sdk";
```

```bash
# MCP — Claude Code / Cursor / Windsurf
fastmcp install claude mcp/synapse_mcp.py
```

## Docs

- [Architecture](docs/architecture.md) — 7-layer technical spec
- [Cognitive Engine](docs/cognitive.md) — memory + reasoning + tools + reflection
- [API Reference](docs/api.md) — endpoints + SDK docs
- [DevOps](docs/devops.md) — deployment guide (Oracle ARM + Coolify)
- [PRD](docs/prd.md) — product requirements + pricing

## AI Agents Building This

Read [AGENTS.md](AGENTS.md) first — it's your complete build context.

## License

MIT
