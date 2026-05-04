-- SynapseOS PostgreSQL Schema
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(64) PRIMARY KEY,
    org_name VARCHAR(128) NOT NULL,
    tier VARCHAR(16) DEFAULT 'starter',
    rpm_limit INTEGER DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL,
    encrypted_key BYTEA NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL,
    source_url TEXT,
    source_filename TEXT,
    minio_raw_path TEXT,
    minio_parsed_path TEXT,
    chunk_count INTEGER DEFAULT 0,
    status VARCHAR(16) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_docs_tenant ON documents(tenant_id, status);

CREATE TABLE IF NOT EXISTS interaction_logs (
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
CREATE INDEX IF NOT EXISTS idx_logs_export ON interaction_logs(tenant_id, ragas_combined)
    WHERE dataset_exported = FALSE;

CREATE TABLE IF NOT EXISTS usage_records (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(16),
    quantity NUMERIC,
    model VARCHAR(64),
    cost NUMERIC(10,6),
    recorded_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage ON usage_records(tenant_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    endpoint_url TEXT,
    method VARCHAR(8) DEFAULT 'GET',
    auth_header BYTEA,
    input_schema JSONB,
    is_builtin BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, name)
);
