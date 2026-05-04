#!/bin/bash
# Initialize MinIO buckets for SynapseOS
# Creates: synapseos, synapse-raw, synapse-parsed (3 buckets)
set -e

MC_ALIAS="synapseos"
MINIO_URL="http://localhost:9000"

# Wait for MinIO to be ready
echo "Waiting for MinIO to be ready..."
until curl -sf ${MINIO_URL}/minio/health/live > /dev/null 2>&1; do
    sleep 2
done
echo "MinIO is live."

# Source .env for credentials
if [ -f .env ]; then
    source .env
fi

: "${MINIO_USER:=synapseos}"
: "${MINIO_PASSWORD:=change-me-to-a-strong-random-string}"

# Configure mc alias (try docker first, fallback to local mc)
if command -v mc > /dev/null 2>&1; then
    MC_CMD="mc"
elif docker run --rm minio/mc version > /dev/null 2>&1; then
    MC_CMD="docker run --rm --network host minio/mc"
else
    echo "❌ Neither 'mc' nor Docker available for MinIO init"
    echo "Install mc: curl -sL https://dl.min.io/client/mc/release/linux-arm64/mc -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc"
    exit 1
fi

$MC_CMD alias set ${MC_ALIAS} ${MINIO_URL} ${MINIO_USER} ${MINIO_PASSWORD}

# Create all required buckets
for BUCKET in synapseos synapse-raw synapse-parsed; do
    if $MC_CMD ls ${MC_ALIAS}/${BUCKET} > /dev/null 2>&1; then
        echo "✅ Bucket '${BUCKET}' already exists"
    else
        $MC_CMD mb ${MC_ALIAS}/${BUCKET}
        echo "✅ Created bucket '${BUCKET}'"
    fi
    # Ensure no anonymous access
    $MC_CMD anonymous set none ${MC_ALIAS}/${BUCKET} 2>/dev/null || true
done

echo ""
echo "✅ All MinIO buckets ready: synapseos, synapse-raw, synapse-parsed"
