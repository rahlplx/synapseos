"""
Shared lazy singletons for Qdrant, KeyDB, MinIO, Fernet.
Replaces duplicate client creation scattered across 10+ files.
All clients are lazy-initialized on first use and reused globally.
"""
import os
import logging
from src.core.config import (
    QDRANT_URL, KEYDB_URL, MINIO_ENDPOINT,
    MINIO_ACCESS_KEY, MINIO_SECRET_KEY, ENCRYPTION_KEY,
    MINIO_RAW_BUCKET, MINIO_PARSED_BUCKET, MINIO_DATASET_BUCKET,
)

logger = logging.getLogger(__name__)

# ─── Qdrant ─────────────────────────────────────────────────────────────────────
_qdrant = None


def get_qdrant():
    """Lazy Qdrant async client singleton."""
    global _qdrant
    if _qdrant is None:
        from qdrant_client import AsyncQdrantClient
        _qdrant = AsyncQdrantClient(url=QDRANT_URL)
    return _qdrant


# ─── KeyDB / Redis ──────────────────────────────────────────────────────────────
_keydb = None


def get_keydb():
    """Lazy KeyDB/Redis async client singleton."""
    global _keydb
    if _keydb is None:
        import redis.asyncio as redis
        _keydb = redis.from_url(KEYDB_URL)
    return _keydb


# ─── MinIO ──────────────────────────────────────────────────────────────────────
_minio = None


def get_minio():
    """Lazy MinIO client singleton. Ensures buckets exist on first use."""
    global _minio
    if _minio is None:
        from minio import Minio
        _minio = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,  # Internal Docker network — no TLS
        )
        # Ensure standard buckets exist
        for bucket in (MINIO_RAW_BUCKET, MINIO_PARSED_BUCKET, MINIO_DATASET_BUCKET):
            try:
                if not _minio.bucket_exists(bucket):
                    _minio.make_bucket(bucket)
            except Exception as e:
                logger.warning(f"[non-critical] MinIO bucket check failed for '{bucket}': {type(e).__name__}: {e}")
    return _minio


# ─── Fernet Cipher ──────────────────────────────────────────────────────────────
_cipher = None


def get_cipher():
    """Lazy Fernet cipher singleton for BYOK key encryption/decryption."""
    global _cipher
    if _cipher is None:
        from cryptography.fernet import Fernet
        if not ENCRYPTION_KEY:
            raise RuntimeError("ENCRYPTION_KEY not configured — required for BYOK encryption")
        _cipher = Fernet(ENCRYPTION_KEY.encode())
    return _cipher


# ─── Cleanup ────────────────────────────────────────────────────────────────────

async def close_all():
    """Gracefully close all async clients. Called on shutdown."""
    global _keydb, _qdrant
    if _keydb is not None:
        await _keydb.aclose()
        _keydb = None
    if _qdrant is not None:
        await _qdrant.close()
        _qdrant = None
    logger.info("[clients] All shared clients closed")
