#!/bin/bash
# SynapseOS Health Check — run from Docker host
# Usage: bash scripts/healthcheck.sh
set -e

echo "=== SynapseOS Health Check ==="
echo ""

PASS=0
FAIL=0

# Qdrant
if curl -sf http://localhost:6333/healthz > /dev/null 2>&1; then
    echo "✅ Qdrant    — healthy (port 6333)"
    PASS=$((PASS+1))
else
    echo "❌ Qdrant    — unreachable"
    FAIL=$((FAIL+1))
fi

# PostgreSQL (via docker exec)
if docker exec synapseos-postgres-1 pg_isready -U synapse -d synapseos > /dev/null 2>&1 || \
   docker exec synapseos_postgres_1 pg_isready -U synapse -d synapseos > /dev/null 2>&1; then
    echo "✅ PostgreSQL — healthy (port 5432)"
    PASS=$((PASS+1))
else
    echo "❌ PostgreSQL — unreachable"
    FAIL=$((FAIL+1))
fi

# KeyDB
if docker exec synapseos-keydb-1 keydb-cli ping > /dev/null 2>&1 || \
   docker exec synapseos_keydb_1 keydb-cli ping > /dev/null 2>&1; then
    echo "✅ KeyDB     — healthy (port 6379)"
    PASS=$((PASS+1))
else
    echo "❌ KeyDB     — unreachable"
    FAIL=$((FAIL+1))
fi

# MinIO
if curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo "✅ MinIO     — healthy (port 9000, console 9001)"
    PASS=$((PASS+1))
else
    echo "❌ MinIO     — unreachable"
    FAIL=$((FAIL+1))
fi

# LiteLLM
if curl -sf http://localhost:4000/health > /dev/null 2>&1; then
    echo "✅ LiteLLM   — healthy (port 4000)"
    PASS=$((PASS+1))
else
    echo "⚠️  LiteLLM   — not ready (may need API keys in .env)"
fi

# FastAPI
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ FastAPI   — healthy (port 8000)"
    PASS=$((PASS+1))
else
    echo "❌ FastAPI   — unreachable"
    FAIL=$((FAIL+1))
fi

# Langfuse
if curl -sf http://localhost:3100/api/health > /dev/null 2>&1; then
    echo "✅ Langfuse  — healthy (port 3100)"
    PASS=$((PASS+1))
else
    echo "⚠️  Langfuse  — not ready (may take longer to start)"
fi

echo ""
# RAM check
FREE=$(free -m 2>/dev/null | awk 'NR==2{print $4}' || echo "unknown")
if [ "$FREE" != "unknown" ]; then
    echo "💾 Free RAM: ${FREE}MB"
    [ "$FREE" -lt 2048 ] && echo "⚠️  Low RAM — check Docling/ONNX usage" || echo "✅ RAM OK"
fi

echo ""
echo "=== Result: ${PASS} passed, ${FAIL} failed ==="
[ "$FAIL" -eq 0 ] && echo "🎉 All services healthy!" || echo "❌ Some services not ready — check: docker compose logs <service>"
