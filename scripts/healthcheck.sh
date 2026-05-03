#!/bin/bash
echo "=== SynapseOS Health Check ==="
curl -sf http://localhost:6333/healthz && echo "✅ Qdrant" || echo "❌ Qdrant"
pg_isready -h localhost -U synapse -d synapseos 2>/dev/null && echo "✅ PostgreSQL" || echo "❌ PostgreSQL"
redis-cli -h localhost ping 2>/dev/null | grep -q PONG && echo "✅ KeyDB" || echo "❌ KeyDB"
curl -sf http://localhost:9000/minio/health/live && echo "✅ MinIO" || echo "❌ MinIO"
curl -sf http://localhost:8000/health && echo "✅ FastAPI" || echo "❌ FastAPI"
curl -sf http://localhost:4000/health 2>/dev/null && echo "✅ LiteLLM" || echo "⚠️  LiteLLM (optional)"
FREE=$(free -m | awk 'NR==2{print $4}')
echo "💾 Free RAM: ${FREE}MB"
[ "$FREE" -lt 2048 ] && echo "⚠️  Low RAM — check Docling/ONNX" || echo "✅ RAM OK"
