#!/usr/bin/env bash
# ─── SynapseOS Local Development Setup ──────────────────────────────────────
# One-command setup: ./scripts/setup-local.sh
#
# Prerequisites: Docker + Docker Compose + Python 3.11+
#
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}━━━ SynapseOS Local Setup ━━━${NC}"

# ── 1. Check prerequisites ────────────────────────────────────────────────
echo -e "\n${YELLOW}[1/6] Checking prerequisites...${NC}"

if ! command -v docker &>/dev/null; then
    echo -e "${RED}Docker not found. Install: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo -e "${RED}Docker Compose not found. Install Docker Compose plugin.${NC}"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3 not found. Install Python 3.11+${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker, Docker Compose, Python3 found${NC}"

# ── 2. Create .env if missing ─────────────────────────────────────────────
echo -e "\n${YELLOW}[2/6] Configuring environment...${NC}"

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Created .env from .env.example${NC}"
    echo -e "${RED}⚠️  You MUST edit .env and add your GROQ_API_KEY${NC}"
    echo -e "   Get free key at: https://console.groq.com → API Keys"
    echo ""
    read -p "Enter your GROQ_API_KEY (or press Enter to edit .env manually later): " GROQ_KEY
    if [ -n "$GROQ_KEY" ]; then
        sed -i "s/gsk_YOUR_GROQ_KEY_HERE/$GROQ_KEY/" .env
        echo -e "${GREEN}✓ GROQ_API_KEY set${NC}"
    fi
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

# ── 3. Start infrastructure services ──────────────────────────────────────
echo -e "\n${YELLOW}[3/6] Starting Docker infrastructure...${NC}"

docker compose -f docker-compose.local.yml up -d

echo "Waiting for services to become healthy..."
sleep 10

# Check each service
for svc in qdrant postgres keydb minio; do
    STATUS=$(docker compose -f docker-compose.local.yml ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health','unknown'))" 2>/dev/null || echo "starting")
    echo -e "  $svc: $STATUS"
done

echo -e "${GREEN}✓ Infrastructure services started${NC}"

# ── 4. Initialize database and storage ────────────────────────────────────
echo -e "\n${YELLOW}[4/6] Initializing database and storage...${NC}"

# Wait for postgres to be ready
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.local.yml exec -T postgres pg_isready -U synapse -d synapseos &>/dev/null; then
        break
    fi
    sleep 1
done

# Run init SQL (mounted as docker-entrypoint-initdb.d, but verify)
echo "Verifying tables exist..."
TABLES=$(docker compose -f docker-compose.local.yml exec -T postgres psql -U synapse -d synapseos -c "\dt" 2>/dev/null || echo "empty")
if echo "$TABLES" | grep -q "tenants"; then
    echo -e "${GREEN}✓ PostgreSQL tables initialized${NC}"
else
    echo "Running init-db.sql manually..."
    docker compose -f docker-compose.local.yml exec -T postgres psql -U synapse -d synapseos < scripts/init-db.sql
    echo -e "${GREEN}✓ PostgreSQL tables created${NC}"
fi

# Initialize MinIO bucket
echo "Setting up MinIO bucket..."
source .env 2>/dev/null || true
if command -v mc &>/dev/null; then
    mc alias set synapseos http://localhost:9000 "${MINIO_USER}" "${MINIO_PASSWORD}" 2>/dev/null || true
    mc mb synapseos/synapseos 2>/dev/null || true
    mc mb synapseos/synapse-raw 2>/dev/null || true
    mc mb synapseos/synapse-parsed 2>/dev/null || true
    echo -e "${GREEN}✓ MinIO buckets created${NC}"
else
    echo -e "${YELLOW}MinIO client (mc) not found. Creating buckets via API..."
    # Use curl to create buckets
    for BUCKET in synapseos synapse-raw synapse-parsed; do
        curl -s -X PUT "http://localhost:9000/${BUCKET}" 2>/dev/null || true
    done
    echo -e "${GREEN}✓ MinIO buckets created (via API)${NC}"
fi

# ── 5. Install Python dependencies ────────────────────────────────────────
echo -e "\n${YELLOW}[5/6] Installing Python dependencies...${NC}"

if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    python3 -m venv .venv
    source .venv/bin/activate
fi

pip install -q --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}✓ Python dependencies installed${NC}"

# ── 6. Create Qdrant collections ──────────────────────────────────────────
echo -e "\n${YELLOW}[6/6] Creating Qdrant collections...${NC}"

source .env
python3 scripts/setup_collection.py

echo -e "${GREEN}✓ Qdrant collections created${NC}"

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━ Setup Complete! ━━━${NC}"
echo ""
echo "Infrastructure services:"
echo "  Qdrant:    http://localhost:6333  (dashboard: http://localhost:6333/dashboard)"
echo "  PostgreSQL: localhost:5432"
echo "  KeyDB:      localhost:6379"
echo "  MinIO:      http://localhost:9000  (console: http://localhost:9001)"
echo "  LiteLLM:    http://localhost:4000"
echo "  Langfuse:   http://localhost:3100"
echo ""
echo "Start the API server:"
echo -e "  ${GREEN}source .venv/bin/activate${NC}"
echo -e "  ${GREEN}source .env${NC}"
echo -e "  ${GREEN}uvicorn src.api.main:app --reload --port 8000${NC}"
echo ""
echo "Test endpoints:"
echo "  curl http://localhost:8000/health"
echo "  curl -X POST http://localhost:8000/v1/query -H 'X-Tenant-ID: test' -H 'Content-Type: application/json' -d '{\"question\":\"hello\",\"stream\":false}'"
echo ""
echo "Run test scripts:"
echo "  python3 scripts/test_ingest.py"
echo "  python3 scripts/test_endpoint.py"
