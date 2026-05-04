# SynapseOS — DevOps

> Target: Oracle ARM A1 (4 vCPU / 24GB RAM) · Coolify · Cloudflare Workers

---

## Directory Structure

```
synapseos/
├── docker-compose.yml
├── .env.production
├── coolify/
│   └── resource-caps.yml
├── cloudflare/
│   └── worker.ts
├── config/
│   ├── qdrant.yaml
│   ├── litellm.yaml
│   └── keydb.conf
├── scripts/
│   ├── init-db.sql
│   ├── init-minio.sh
│   └── healthcheck.sh
└── src/
    └── ...
```

---

## Docker Compose (Full Stack)

```yaml
# docker-compose.yml
version: "3.9"

x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"

services:

  # ─── Vector Database ───
  qdrant:
    image: qdrant/qdrant:v1.13.5
    restart: unless-stopped
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/var/lib/qdrant/storage
      - ./config/qdrant.yaml:/qdrant/config/production.yaml
    environment:
      - QDRANT__STORAGE__PERFORMANCE__ASYNC_SCORER=true    # ARM io_uring
      - QDRANT__STORAGE__STORAGE_PATH=/var/lib/qdrant/storage
      - QDRANT__LOG_LEVEL=WARN
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: "4G"
        reservations:
          memory: "1G"
    logging: *default-logging

  # ─── Relational Database ───
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_DB=synapseos
      - POSTGRES_USER=synapse
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "2G"
    logging: *default-logging

  # ─── Cache + Queue + Rate Limit ───
  keydb:
    image: eqalpha/keydb:latest
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - keydb_data:/data
      - ./config/keydb.conf:/etc/keydb/keydb.conf
    command: keydb-server /etc/keydb/keydb.conf
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "1.5G"
    logging: *default-logging

  # ─── Object Storage ───
  minio:
    image: minio/minio:latest
    restart: unless-stopped
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "1G"
    logging: *default-logging

  # ─── LiteLLM Proxy ───
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    restart: unless-stopped
    ports:
      - "4000:4000"
    volumes:
      - ./config/litellm.yaml:/app/config.yaml
    environment:
      - REDIS_URL=redis://keydb:6379
    command: --config /app/config.yaml --port 4000
    depends_on:
      - keydb
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "512M"
    logging: *default-logging

  # ─── FastAPI Backend ───
  api:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://synapse:${POSTGRES_PASSWORD}@postgres:5432/synapseos
      - QDRANT_URL=http://qdrant:6333
      - KEYDB_URL=redis://keydb:6379
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_USER}
      - MINIO_SECRET_KEY=${MINIO_PASSWORD}
      - LITELLM_URL=http://litellm:4000
      - LANGFUSE_HOST=http://langfuse:3100
      - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY}
      - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - OMP_NUM_THREADS=4
    depends_on:
      - postgres
      - qdrant
      - keydb
      - minio
      - litellm
    deploy:
      resources:
        limits:
          cpus: "3.0"
          memory: "6G"
        reservations:
          cpus: "0.5"
          memory: "1.5G"
    logging: *default-logging

  # ─── Ingestion Worker (separate container — concurrency=1) ───
  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql+asyncpg://synapse:${POSTGRES_PASSWORD}@postgres:5432/synapseos
      - QDRANT_URL=http://qdrant:6333
      - KEYDB_URL=redis://keydb:6379
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_USER}
      - MINIO_SECRET_KEY=${MINIO_PASSWORD}
      - OMP_NUM_THREADS=4
      - DOCLING_CPU_ONLY=1
    depends_on:
      - keydb
      - qdrant
      - minio
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: "4.5G"   # Docling peak
    logging: *default-logging

  # ─── MCP Server ───
  mcp:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    restart: unless-stopped
    ports:
      - "8095:8095"
    environment:
      - SYNAPSE_BASE_URL=http://api:8000
      - SYNAPSE_API_KEY=${MCP_SERVICE_KEY}
    deploy:
      resources:
        limits:
          cpus: "0.2"
          memory: "256M"

  # ─── Observability ───
  langfuse:
    image: langfuse/langfuse:3
    restart: unless-stopped
    ports:
      - "3100:3000"
    environment:
      - DATABASE_URL=postgresql://synapse:${POSTGRES_PASSWORD}@postgres:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_NEXTAUTH_SECRET}
      - SALT=${LANGFUSE_SALT}
      - NEXTAUTH_URL=http://localhost:3100
    depends_on:
      - postgres
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: "2.5G"
    logging: *default-logging

volumes:
  qdrant_data:
  pg_data:
  keydb_data:
  minio_data:
```

---

## Qdrant Server Config

```yaml
# config/qdrant.yaml
storage:
  storage_path: /var/lib/qdrant/storage
  snapshots_path: /var/lib/qdrant/snapshots
  performance:
    max_search_threads: 4
    async_scorer: true          # ARM io_uring
  optimizers:
    default_segment_number: 2
    memmap_threshold_kb: 50000
    indexing_threshold_kb: 100000
    max_segment_size_kb: 65536
  hnsw_index:
    m: 16
    ef_construct: 100
    full_scan_threshold_kb: 10000
    max_indexing_threads: 4
```

---

## KeyDB Config

```conf
# config/keydb.conf

# Multi-threading (ARM 4 vCPU)
server-threads 2

# Memory
maxmemory 1536mb
maxmemory-policy allkeys-lru

# Persistence — AOF only (RDB causes fork() OOM on ARM)
appendonly yes
appendfsync everysec
no-appendfsync-on-rewrite yes
save ""                         # DISABLE RDB snapshots

# Network
bind 0.0.0.0
port 6379
tcp-keepalive 300
```

---

## LiteLLM Config

```yaml
# config/litellm.yaml
model_list:
  - model_name: "default"
    litellm_params:
      model: "groq/llama-3.1-8b-instant"
      api_key: "os.environ/GROQ_API_KEY"
  - model_name: "default-fallback-1"
    litellm_params:
      model: "openrouter/meta-llama/llama-3.1-8b-instruct"
      api_key: "os.environ/OPENROUTER_API_KEY"
  - model_name: "default-fallback-2"
    litellm_params:
      model: "anthropic/claude-haiku-4-5"
      api_key: "os.environ/ANTHROPIC_API_KEY"

router_settings:
  routing_strategy: "latency-based-routing"
  num_retries: 1
  timeout: 30
  fallbacks:
    - {"default": ["default-fallback-1", "default-fallback-2"]}

litellm_settings:
  forward_llm_provider_auth_headers: true   # BYOK key pass-through
  cache: true
  cache_params:
    type: redis
    host: keydb
    port: 6379
    semantic_cache:
      enabled: true
      embedding_model: "BAAI/bge-base-en-v1.5"
      similarity_threshold: 0.92
```

---

## Cloudflare Workers Edge Proxy

```typescript
// cloudflare/worker.ts

export interface Env {
  RAG_CACHE: KVNamespace;
  ORACLE_BACKEND: string;       // https://api.synapseos.com
  CACHE_TTL: number;            // 3600
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only cache POST /v1/query
    const url = new URL(request.url);
    if (request.method !== "POST" || !url.pathname.includes("/query")) {
      return fetch(env.ORACLE_BACKEND + url.pathname, request);
    }

    const cloned = request.clone();
    const body = await cloned.text();

    // SHA-256 hash of full request body (includes question + tenant headers)
    const hashBuffer = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(
        body + (request.headers.get("X-Tenant-ID") ?? "")
      )
    );
    const cacheKey = Array.from(new Uint8Array(hashBuffer))
      .map(b => b.toString(16).padStart(2, "0"))
      .join("");

    // Check KV cache
    const cached = await env.RAG_CACHE.get(cacheKey);
    if (cached) {
      return new Response(cached, {
        headers: {
          "Content-Type": "application/json",
          "X-Cache-Status": "HIT",
          "X-Cache-Key": cacheKey.slice(0, 8),
        },
      });
    }

    // Forward to Oracle ARM
    const backendResp = await fetch(
      env.ORACLE_BACKEND + url.pathname,
      new Request(request, { body })
    );

    if (backendResp.ok && !body.includes('"stream":true')) {
      // Only cache non-streaming responses
      const respClone = backendResp.clone();
      const respText = await respClone.text();
      await env.RAG_CACHE.put(cacheKey, respText, {
        expirationTtl: env.CACHE_TTL ?? 3600,
      });
    }

    return backendResp;
  },
};
```

**Deploy**:
```bash
wrangler deploy cloudflare/worker.ts --name synapseos-edge
wrangler kv:namespace create RAG_CACHE
# Add KV namespace ID to wrangler.toml
```

---

## Environment Variables

```bash
# .env.production

# Database
POSTGRES_PASSWORD=<strong-random>

# MinIO
MINIO_USER=synapseos
MINIO_PASSWORD=<strong-random>

# Encryption (BYOK keys at rest)
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=<base64-32-byte-key>

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_NEXTAUTH_SECRET=<random-32-char>
LANGFUSE_SALT=<random-32-char>

# LLM providers (platform defaults — tenants override via BYOK)
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
ANTHROPIC_API_KEY=sk-ant-...

# MCP service key
MCP_SERVICE_KEY=sk-syn-mcp-...
```

---

## Init DB Script

```sql
-- scripts/init-db.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE tenants (
    id VARCHAR(64) PRIMARY KEY,
    org_name VARCHAR(128) NOT NULL,
    tier VARCHAR(16) DEFAULT 'starter',
    rpm_limit INTEGER DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL,
    encrypted_key BYTEA NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL,
    source_url TEXT,
    minio_raw_path TEXT,
    minio_parsed_path TEXT,
    chunk_count INTEGER DEFAULT 0,
    status VARCHAR(16) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_docs_tenant ON documents(tenant_id, status);

CREATE TABLE interaction_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    contexts JSONB NOT NULL,
    trace_id VARCHAR(128),
    ragas_faithfulness NUMERIC(4,3),
    ragas_relevancy NUMERIC(4,3),
    ragas_precision NUMERIC(4,3),
    ragas_combined NUMERIC(4,3),
    user_feedback SMALLINT,
    dataset_exported BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_logs_export ON interaction_logs(tenant_id, ragas_combined)
    WHERE dataset_exported = FALSE;

CREATE TABLE usage_records (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(16),
    quantity NUMERIC,
    model VARCHAR(64),
    cost NUMERIC(10,6),
    recorded_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_usage ON usage_records(tenant_id, recorded_at DESC);

-- Langfuse gets its own DB (created separately in Coolify)
```

---

## Healthcheck Script

```bash
#!/bin/bash
# scripts/healthcheck.sh

echo "=== SynapseOS Health ==="

# Qdrant
curl -sf http://localhost:6333/healthz && echo "✅ Qdrant" || echo "❌ Qdrant"

# PostgreSQL
pg_isready -h localhost -U synapse -d synapseos && echo "✅ PostgreSQL" || echo "❌ PostgreSQL"

# KeyDB
redis-cli -h localhost ping | grep -q PONG && echo "✅ KeyDB" || echo "❌ KeyDB"

# MinIO
curl -sf http://localhost:9000/minio/health/live && echo "✅ MinIO" || echo "❌ MinIO"

# FastAPI
curl -sf http://localhost:8000/health && echo "✅ FastAPI" || echo "❌ FastAPI"

# LiteLLM
curl -sf http://localhost:4000/health && echo "✅ LiteLLM" || echo "❌ LiteLLM"

# Langfuse
curl -sf http://localhost:3100/api/public/health && echo "✅ Langfuse" || echo "❌ Langfuse"

# RAM check
FREE=$(free -m | awk 'NR==2{print $4}')
echo "💾 Free RAM: ${FREE}MB"
if [ "$FREE" -lt 2048 ]; then
  echo "⚠️  WARNING: Low RAM — check for Docling/ONNX leak"
fi
```

---

## Coolify Deployment Steps

1. Add Oracle ARM server to Coolify (SSH key auth)
2. Create new `Docker Compose` service, paste `docker-compose.yml`
3. Set all environment variables in Coolify Secrets panel
4. Enable Coolify Traefik for HTTPS on `api.synapseos.com`
5. Deploy — Coolify applies resource caps from `deploy.resources.limits`
6. Run `./scripts/healthcheck.sh` to verify all services green
7. Deploy Cloudflare Worker: `wrangler deploy`
8. Set `ORACLE_BACKEND` Worker variable to your API domain

---

## Monitoring Setup

**Langfuse** (self-hosted at `:3100`):
- View trace timeline per query
- Filter by `tenant_id` metadata
- Export evaluation datasets for fine-tuning

**Coolify metrics**:
- Container RAM / CPU per service
- Watch for Docling worker memory spikes

**PostgreSQL query to watch**:
```sql
-- RAGAS score trend last 7 days
SELECT
  date_trunc('day', created_at) AS day,
  AVG(ragas_faithfulness) AS faithfulness,
  AVG(ragas_relevancy) AS relevancy,
  AVG(ragas_combined) AS combined,
  COUNT(*) AS queries
FROM interaction_logs
WHERE created_at > now() - INTERVAL '7 days'
GROUP BY 1
ORDER BY 1;
```
