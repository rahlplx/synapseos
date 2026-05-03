#!/bin/bash
# Initialize MinIO buckets for SynapseOS
MC_ALIAS="synapseos"
MINIO_URL="http://localhost:9000"

# Wait for MinIO to be ready
until curl -sf ${MINIO_URL}/minio/health/live; do
    echo "Waiting for MinIO..."
    sleep 2
done

# Configure mc alias
docker run --rm --network host \
    minio/mc alias set ${MC_ALIAS} ${MINIO_URL} ${MINIO_USER} ${MINIO_PASSWORD}

# Create bucket
docker run --rm --network host \
    minio/mc mb --ignore-existing ${MC_ALIAS}/synapseos

# Set bucket policy
docker run --rm --network host \
    minio/mc anonymous set none ${MC_ALIAS}/synapseos

echo "✅ MinIO bucket 'synapseos' ready"
