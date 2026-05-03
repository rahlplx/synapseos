"""Shared test fixtures for SynapseOS."""
import os
import pytest

# Set test environment
os.environ.setdefault("GROQ_API_KEY", "test_key")
os.environ.setdefault("ENCRYPTION_KEY", "46Z1dGGVq3_iHijlZn3m0FG1bfIQE9XuqVAerUmgFqQ=")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("KEYDB_URL", "redis://localhost:6379")
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://synapse:testpass@localhost:5432/synapseos")
os.environ.setdefault("MINIO_USER", "synapseos")
os.environ.setdefault("MINIO_PASSWORD", "testpass")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")

@pytest.fixture
def tenant_id():
    return "test-tenant-001"

@pytest.fixture  
def base_url():
    return "http://localhost:8000"
