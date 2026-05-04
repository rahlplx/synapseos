#!/bin/bash
# SynapseOS Cloudflare Worker Deployment Script
# Run from repo root: bash cloudflare/deploy.sh
set -e

echo "=== SynapseOS — Cloudflare Worker Deployment ==="
echo ""

# Step 1: Install wrangler
echo "Step 1: Installing Wrangler CLI..."
if ! command -v wrangler &> /dev/null; then
    npm install -g wrangler
    echo "✅ Wrangler installed"
else
    echo "✅ Wrangler already installed: $(wrangler --version)"
fi

# Step 2: Login to Cloudflare
echo ""
echo "Step 2: Logging in to Cloudflare..."
echo "A browser window will open. Please authorize."
wrangler login
echo "✅ Logged in"

# Step 3: Create KV namespace
echo ""
echo "Step 3: Creating KV namespace for RAG cache..."
KV_OUTPUT=$(wrangler kv namespace create RAG_CACHE 2>&1)
echo "$KV_OUTPUT"

# Extract namespace ID from output
KV_ID=$(echo "$KV_OUTPUT" | grep -oP 'id = "\K[^"]+' || echo "")
if [ -z "$KV_ID" ]; then
    echo "⚠️  Could not auto-extract KV namespace ID."
    echo "Please look at the output above and find the 'id' value."
    read -p "Enter KV namespace ID: " KV_ID
fi
echo "✅ KV namespace ID: $KV_ID"

# Step 4: Update wrangler.toml with real namespace ID
echo ""
echo "Step 4: Updating wrangler.toml..."
sed -i "s/REPLACE_WITH_YOUR_KV_NAMESPACE_ID/$KV_ID/" cloudflare/wrangler.toml
echo "✅ wrangler.toml updated"

# Step 5: Set ORACLE_BACKEND secret
echo ""
echo "Step 5: Setting ORACLE_BACKEND secret..."
echo "This is the URL of your Oracle ARM server (e.g., https://synapseos.yourdomain.com)"
wrangler secret put ORACLE_BACKEND

# Step 6: Deploy
echo ""
echo "Step 6: Deploying worker..."
cd cloudflare
wrangler deploy
cd ..
echo "✅ Worker deployed"

# Step 7: Test
echo ""
echo "Step 7: Testing cache behavior..."
echo ""
echo "Run these commands to verify:"
echo ""
echo "# First request (should be MISS):"
echo 'curl -s -D - -o /dev/null -X POST https://synapseos-edge.<your-subdomain>.workers.dev/v1/query \'
echo '  -H "X-Tenant-ID: test" -H "Content-Type: application/json" \'
echo '  -d '"'"'{"question":"what is Qdrant?","stream":false}'"'"' | grep X-Cache-Status'
echo ""
echo "# Second identical request (should be HIT):"
echo 'curl -s -D - -o /dev/null -X POST https://synapseos-edge.<your-subdomain>.workers.dev/v1/query \'
echo '  -H "X-Tenant-ID: test" -H "Content-Type: application/json" \'
echo '  -d '"'"'{"question":"what is Qdrant?","stream":false}'"'"' | grep X-Cache-Status'
echo ""
echo "=== Deployment Complete ==="
