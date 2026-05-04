#!/bin/bash
# SynapseOS — /v1/think Demo Script
# Pretty-prints the full cognitive engine response
# Usage: bash scripts/demo.sh

API_URL="${SYNAPSE_API_URL:-http://localhost:8000}"
TENANT="${SYNAPSE_TENANT:-test}"

echo "=== SynapseOS — Cognitive Engine Demo ==="
echo "API: $API_URL | Tenant: $TENANT"
echo ""

QUESTION="${1:-What is hybrid retrieval and how does SynapseOS use it for RAG?}"

echo "Question: $QUESTION"
echo "Sending to /v1/think..."
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/v1/think" \
  -H "X-Tenant-ID: $TENANT" \
  -H "Content-Type: application/json" \
  -d "{
    \"question\": \"$QUESTION\",
    \"session_id\": \"demo-$(date +%s)\",
    \"user_id\": \"demo-user\",
    \"stream\": false
  }")

# Pretty-print JSON if jq is available
if command -v jq &> /dev/null; then
    echo "$RESPONSE" | jq .
else
    echo "$RESPONSE"
fi

echo ""
echo "=== Demo Complete ==="
echo "Try: bash scripts/demo.sh \"What is my name?\""
echo "Try: bash scripts/demo.sh \"Search the web for Qdrant latest release\""
