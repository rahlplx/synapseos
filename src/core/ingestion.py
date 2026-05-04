"""
L1 — Ingestion Engine
Crawl4AI → Docling → SemanticChunker → SHA-256 dedup → sanitise → fastembed → Qdrant + MinIO + PG
ARM: Docling concurrency=1, batch_size=64 ingestion, OMP_NUM_THREADS=4
Security: Prompt injection sanitisation strips known injection patterns before embedding.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")          # ARM CPU tuning — MUST be before fastembed
os.environ.setdefault("DOCLING_CPU_ONLY", "1")         # ARM: force Docling CPU-only mode

import asyncio
import hashlib
import tempfile
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import AsyncQdrantClient, models
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
import redis.asyncio as redis
import asyncpg
import boto3
from botocore.client import Config

# ─── Clients ──────────────────────────────────────────────────────────────────
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
KEYDB_URL = os.environ.get("KEYDB_URL", "redis://keydb:6379")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://synapse:changeme@postgres:5432/synapseos")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "synapseos")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "changeme")
COLLECTION = "synapse_knowledge"

qdrant = AsyncQdrantClient(url=QDRANT_URL)
keydb = redis.from_url(KEYDB_URL)

# ─── MinIO Client (lazy) ─────────────────────────────────────────────────────
_minio_client = None
MINIO_RAW_BUCKET = "synapse-raw"
MINIO_PARSED_BUCKET = "synapse-parsed"


def _get_minio():
    """Lazy-initialize MinIO client and ensure buckets exist."""
    global _minio_client
    if _minio_client is None:
        from minio import Minio
        _minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,  # Internal Docker network — no TLS
        )
        # Ensure buckets exist
        for bucket in (MINIO_RAW_BUCKET, MINIO_PARSED_BUCKET):
            if not _minio_client.bucket_exists(bucket):
                _minio_client.make_bucket(bucket)
    return _minio_client


# ─── PostgreSQL pool (lazy) ──────────────────────────────────────────────────
_pg_pool = None


async def _get_pg():
    """Get the shared asyncpg connection pool."""
    from src.core.db import get_pool
    return await get_pool()


# ─── Models (lazy_load=True — only allocate RAM on first embed call) ──────────
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)

# ─── ARM Constants ────────────────────────────────────────────────────────────
INGEST_BATCH_SIZE = 64   # batch_size=64 for ingestion (architecture doc)
SCROLL_DELAY = 1.5       # Crawl4AI scroll delay for full page render


# ─── MinIO Helpers ────────────────────────────────────────────────────────────

async def store_raw_to_minio(content: bytes, object_key: str) -> str:
    """Store raw content bytes in MinIO. Returns the object key.
    Uses asyncio.to_thread to avoid blocking the event loop.
    """
    client = _get_minio()
    import io
    data_stream = io.BytesIO(content)
    await asyncio.to_thread(
        client.put_object,
        MINIO_RAW_BUCKET,
        object_key,
        data_stream,
        len(content),
        content_type="application/octet-stream",
    )
    return object_key


async def store_parsed_to_minio(markdown: str, object_key: str) -> str:
    """Store parsed markdown in MinIO. Returns the object key.
    Uses asyncio.to_thread to avoid blocking the event loop.
    """
    client = _get_minio()
    import io
    content_bytes = markdown.encode("utf-8")
    data_stream = io.BytesIO(content_bytes)
    await asyncio.to_thread(
        client.put_object,
        MINIO_PARSED_BUCKET,
        object_key,
        data_stream,
        len(content_bytes),
        content_type="text/markdown",
    )
    return object_key


# ─── PostgreSQL Helpers ───────────────────────────────────────────────────────

async def upsert_document_record(
    tenant_id: str,
    source_url: Optional[str],
    source_filename: Optional[str],
    minio_raw_path: Optional[str],
    minio_parsed_path: Optional[str],
    chunk_count: int,
    status: str,
) -> str:
    """Insert or update a document record in PostgreSQL.
    Returns the document UUID.
    """
    doc_id = str(uuid4())
    pool = await _get_pg()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, tenant_id, source_url, minio_raw_path, minio_parsed_path, chunk_count, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            doc_id,
            tenant_id,
            source_url,
            minio_raw_path,
            minio_parsed_path,
            chunk_count,
            status,
            datetime.now(timezone.utc),
        )
    return doc_id


async def update_document_status(doc_id: str, status: str, chunk_count: int = None):
    """Update document status and optionally chunk count in PostgreSQL."""
    pool = await _get_pg()
    async with pool.acquire() as conn:
        if chunk_count is not None:
            await conn.execute(
                "UPDATE documents SET status=$2, chunk_count=$3 WHERE id=$1",
                doc_id, status, chunk_count,
            )
        else:
            await conn.execute(
                "UPDATE documents SET status=$2 WHERE id=$1",
                doc_id, status,
            )


async def log_interaction(
    tenant_id: str,
    event_type: str,
    detail: dict,
):
    """Write an interaction log to PostgreSQL after ingestion events.
    Records ingestion metadata for audit, analytics, and self-improvement loop.
    """
    import json
    pool = await _get_pg()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interaction_logs (id, tenant_id, query, answer, contexts, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            str(uuid4()),
            tenant_id,
            f"[ingestion:{event_type}]",
            json.dumps(detail),
            json.dumps([]),
            datetime.now(timezone.utc),
        )


async def close_ingestion_clients():
    """Gracefully close async clients. Called on shutdown."""
    from src.core.db import close_pool
    await close_pool()


# ─── Core Pipeline ────────────────────────────────────────────────────────────

async def scrape_url(url: str) -> str:
    """Scrape a URL using Crawl4AI with JS rendering and pruning content filter.
    ARM gotcha: Only 1 concurrent Chromium process on this budget.
    """
    md_gen = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.48)
    )
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_gen,
        page_timeout=30000,       # 30s hard timeout — prevents DOM hang
        scan_full_page=True,
        scroll_delay=SCROLL_DELAY,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        if not result.markdown or not result.markdown.fit_markdown:
            raise ValueError(f"Scraping returned empty content for {url}")
        return result.markdown.fit_markdown


def parse_document(file_bytes: bytes, filename: str) -> str:
    """Parse a PDF/DOCX file using Docling (layout-aware → markdown).
    ARM gotcha: Docling peaks at ~3.5GB RAM per 100-page PDF.
    Queue concurrency MUST be 1. DOCLING_CPU_ONLY=1 enforced above.
    """
    from docling.document_converter import DocumentConverter

    suffix = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        tmp_path = f.name
    try:
        converter = DocumentConverter()
        doc = converter.convert(source=f"file://{tmp_path}")
        markdown = doc.export_to_markdown()
        if not markdown or not markdown.strip():
            raise ValueError(f"Docling returned empty content for {filename}")
        return markdown
    finally:
        os.unlink(tmp_path)


def semantic_chunk(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    """Split text into semantic chunks using the semchunk library.
    chunk_size=512 tokens, overlap=64 tokens (architecture doc).
    Uses tiktoken for accurate token counting (cl100k_base = GPT-4 tokenizer).
    """
    from semchunk import chunk
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")

    def token_counter(t: str) -> int:
        return len(enc.encode(t))

    chunks = chunk(
        text,
        chunk_size=max_tokens,
        token_counter=token_counter,
    )
    if not chunks:
        raise ValueError("Semantic chunking produced zero chunks — input may be too short")
    return chunks


# ─── Prompt Injection Sanitiser ────────────────────────────────────────────────
# OWASP LLM Top 10: Prompt injection through ingested content is a critical risk
# for multi-tenant RAG systems. Any tenant can ingest any URL — malicious content
# in scraped pages becomes an injection vector when retrieved into LLM context.

INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above|prior)\s+instructions?",
    r"system\s*prompt",
    r"you\s+are\s+now",
    r"disregard\s+(your|all|previous)\s+(instructions?|rules?)",
    r"forget\s+(everything|all|what)",
    r"new\s+(role|persona|identity|instructions?)",
    r"override\s+(previous|all|safety)\s+(instructions?|rules?|guidelines?)",
    r"act\s+as\s+(if\s+you\s+(are|were)|a\s+different)",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
]

import re as _re
_injection_regex = _re.compile("|".join(INJECTION_PATTERNS), _re.IGNORECASE)

_SANITIZE_LOG = None


def _get_sanitize_logger():
    """Lazy logger to avoid import-time issues."""
    global _SANITIZE_LOG
    if _SANITIZE_LOG is None:
        import logging
        _SANITIZE_LOG = logging.getLogger(__name__)
    return _SANITIZE_LOG


def sanitise_chunk(text: str, tenant_id: str = "") -> str | None:
    """Sanitise a chunk for prompt injection patterns.

    Returns None if the chunk contains a likely injection attempt —
    such chunks should be SKIPPED (not embedded).

    Returns cleaned text with HTML artifacts stripped if the chunk
    passes the injection check.

    This prevents the OWASP LLM Top 10 vulnerability where malicious
    content scraped from URLs manipulates the LLM when retrieved.
    """
    lower = text.lower()

    # Check for injection patterns
    if _injection_regex.search(lower):
        _get_sanitize_logger().warning(
            f"[security] Prompt injection attempt blocked for tenant={tenant_id}: "
            f"{text[:100]}..."
        )
        return None

    # Strip HTML artifacts that might bypass the markdown parser
    text = _re.sub(r'<script[^>]*>.*?</script>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<[^>]+>', '', text)  # Remove remaining HTML tags
    text = text.strip()

    return text if text else None


async def dedup_chunks(chunks: list[str], tenant_id: str) -> list[str]:
    """SHA-256 dedup — check KeyDB set per tenant.
    Prevents re-ingesting identical chunks on repeated scrapes.
    """
    unique = []
    for chunk in chunks:
        h = hashlib.sha256(chunk.encode()).hexdigest()
        added = await keydb.sadd(f"tenant:{tenant_id}:hashes", h)
        if added:
            unique.append(chunk)
    return unique


async def embed_and_upsert(chunks: list[str], tenant_id: str, metadata: dict):
    """Generate dual vectors (dense 768d + sparse BM25) and upsert to Qdrant.
    batch_size=64 for ingestion per ARM rules.
    Sparse vectors use models.SparseVector(indices=..., values=...) for
    compatibility with newer qdrant-client API versions.
    Chunks are sanitised for prompt injection before embedding.
    """
    if not chunks:
        return

    # Sanitise chunks — skip any that contain prompt injection attempts
    clean_chunks = []
    for c in chunks:
        result = sanitise_chunk(c, tenant_id)
        if result is not None:
            clean_chunks.append(result)
        # else: injection attempt blocked and logged — skip embedding

    if not clean_chunks:
        _get_sanitize_logger().warning(
            f"[security] All chunks for tenant={tenant_id} blocked by sanitiser"
        )
        return

    chunks = clean_chunks

    dense_vecs = list(dense_model.embed(chunks, batch_size=INGEST_BATCH_SIZE))
    sparse_vecs = list(sparse_model.embed(chunks, batch_size=INGEST_BATCH_SIZE))

    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector={
                "dense": dense_vecs[i].tolist(),
                "sparse": models.SparseVector(
                    indices=sparse_vecs[i].indices.tolist(),
                    values=sparse_vecs[i].values.tolist(),
                ),
            },
            payload={"text": chunks[i], "tenant_id": tenant_id, **metadata},
        )
        for i in range(len(chunks))
    ]
    await qdrant.upsert(collection_name=COLLECTION, points=points)



async def archive_to_minio(tenant_id: str, doc_id: str, raw_content: str, parsed_md: str):
    """Archive raw + parsed content to MinIO. Fire-and-forget safe."""
    try:
        minio = boto3.client(
            "s3",
            endpoint_url=f"http://{os.environ.get('MINIO_ENDPOINT', 'minio:9000')}",
            aws_access_key_id=os.environ.get("MINIO_USER", "synapseos"),
            aws_secret_access_key=os.environ.get("MINIO_PASSWORD", ""),
            config=Config(signature_version="s3v4"),
        )
        bucket = "synapseos"
        # Raw
        minio.put_object(
            Bucket=bucket,
            Key=f"{tenant_id}/raw/{doc_id}.txt",
            Body=raw_content.encode(),
            ContentType="text/plain",
        )
        # Parsed markdown
        minio.put_object(
            Bucket=bucket,
            Key=f"{tenant_id}/parsed/{doc_id}.md",
            Body=parsed_md.encode(),
            ContentType="text/markdown",
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[non-critical] archive_to_minio failed: {type(e).__name__}: {e}")
        # MinIO failure must never block ingestion

async def ingest_urls(
    urls: list[str],
    tenant_id: str,
    job_id: str,
    metadata: Optional[dict] = None,
):
    """Ingest a list of URLs: scrape → chunk → dedup → embed → upsert.
    Stores raw content in MinIO, writes document records to PostgreSQL,
    and logs ingestion events to interaction_logs.
    Updates job status in KeyDB for polling.
    """
    metadata = metadata or {}
    await keydb.hset(f"job:{job_id}", mapping={"status": "processing", "total": len(urls), "done": 0})

    total_chunks = 0

    for url in urls:
        doc_id = None
        try:
            # 1. Scrape
            await keydb.hset(f"job:{job_id}", "current_url", url)
            markdown = await scrape_url(url)

            # 2. Store raw content in MinIO
            raw_key = f"{tenant_id}/urls/{job_id}/{hashlib.sha256(url.encode()).hexdigest()[:16]}.md"
            await store_raw_to_minio(markdown.encode("utf-8"), raw_key)

            # 3. Store parsed markdown in MinIO
            parsed_key = f"{tenant_id}/parsed/{job_id}/{hashlib.sha256(url.encode()).hexdigest()[:16]}.md"
            await store_parsed_to_minio(markdown, parsed_key)

            # 4. Create PostgreSQL document record
            doc_id = await upsert_document_record(
                tenant_id=tenant_id,
                source_url=url,
                source_filename=None,
                minio_raw_path=f"{MINIO_RAW_BUCKET}/{raw_key}",
                minio_parsed_path=f"{MINIO_PARSED_BUCKET}/{parsed_key}",
                chunk_count=0,
                status="processing",
            )

            # 5. Chunk
            chunks = semantic_chunk(markdown)

            # 6. Dedup
            unique = await dedup_chunks(chunks, tenant_id)

            # 7. Embed + Upsert
            await embed_and_upsert(unique, tenant_id, {**metadata, "source_url": url})

            # 8. Update PostgreSQL document record with final chunk count
            await update_document_status(doc_id, "done", chunk_count=len(unique))

            # 9. Extract entities for graph queries (fire-and-forget)
            asyncio.create_task(_extract_and_store_entities(markdown, tenant_id, doc_id))

            # 10. Log ingestion event to interaction_logs
            await log_interaction(
                tenant_id=tenant_id,
                event_type="url_ingest",
                detail={
                    "job_id": job_id,
                    "url": url,
                    "doc_id": doc_id,
                    "chunk_count": len(unique),
                    "minio_raw_path": f"{MINIO_RAW_BUCKET}/{raw_key}",
                },
            )

            total_chunks += len(unique)

            # 10. Update progress
            done_count = int(await keydb.hget(f"job:{job_id}", "done") or 0)
            await keydb.hset(f"job:{job_id}", "done", done_count + 1)
        except Exception as e:
            if doc_id:
                await update_document_status(doc_id, "failed")
            await keydb.hset(f"job:{job_id}", f"error:{url}", str(e)[:500])

    await keydb.hset(f"job:{job_id}", mapping={"status": "done", "chunk_count": total_chunks})
    # Set job TTL to 24 hours so it auto-cleans
    await keydb.expire(f"job:{job_id}", 86400)


async def ingest_file(
    file_bytes: bytes,
    filename: str,
    tenant_id: str,
    job_id: str,
):
    """Ingest an uploaded file: parse → chunk → dedup → embed → upsert.
    Stores raw file in MinIO, writes document record to PostgreSQL,
    and logs ingestion event to interaction_logs.
    Docling concurrency=1 enforced at worker level. DOCLING_CPU_ONLY=1 set above.
    """
    doc_id = None
    await keydb.hset(f"job:{job_id}", "status", "processing")
    try:
        # 1. Store raw file in MinIO
        raw_key = f"{tenant_id}/files/{job_id}/{filename}"
        await store_raw_to_minio(file_bytes, raw_key)

        # 2. Parse document
        markdown = parse_document(file_bytes, filename)

        # 3. Store parsed markdown in MinIO
        parsed_key = f"{tenant_id}/parsed/{job_id}/{filename}.md"
        await store_parsed_to_minio(markdown, parsed_key)

        # 4. Create PostgreSQL document record
        doc_id = await upsert_document_record(
            tenant_id=tenant_id,
            source_url=None,
            source_filename=filename,
            minio_raw_path=f"{MINIO_RAW_BUCKET}/{raw_key}",
            minio_parsed_path=f"{MINIO_PARSED_BUCKET}/{parsed_key}",
            chunk_count=0,
            status="processing",
        )

        # 5. Chunk
        chunks = semantic_chunk(markdown)

        # 6. Dedup
        unique = await dedup_chunks(chunks, tenant_id)

        # 7. Embed + Upsert
        await embed_and_upsert(unique, tenant_id, {"source_filename": filename})

        # 8. Update PostgreSQL document record with final chunk count
        await update_document_status(doc_id, "done", chunk_count=len(unique))

        # 9. Extract entities for graph queries (fire-and-forget)
        asyncio.create_task(_extract_and_store_entities(markdown, tenant_id, doc_id))

        # 10. Log ingestion event to interaction_logs
        await log_interaction(
            tenant_id=tenant_id,
            event_type="file_ingest",
            detail={
                "job_id": job_id,
                "filename": filename,
                "doc_id": doc_id,
                "chunk_count": len(unique),
                "minio_raw_path": f"{MINIO_RAW_BUCKET}/{raw_key}",
            },
        )

        # 10. Record chunk count in KeyDB job
        await keydb.hset(f"job:{job_id}", mapping={"status": "done", "chunk_count": len(unique)})
    except Exception as e:
        if doc_id:
            await update_document_status(doc_id, "failed")
        await keydb.hset(f"job:{job_id}", mapping={"status": "failed", "error": str(e)[:500]})

    # Set job TTL to 24 hours
    await keydb.expire(f"job:{job_id}", 86400)


# ─── Entity Extraction (LazyGraphRAG) ───────────────────────────────────────
# Lightweight entity extraction for cross-document relationship queries.
# Uses Groq 8b (~$0.0001 per document) + PostgreSQL — no new infrastructure.
# Fire-and-forget via asyncio.create_task() — never blocks ingestion.

async def _extract_and_store_entities(text: str, tenant_id: str, doc_id: str):
    """Extract named entities from text and upsert to entities table.

    Uses Groq 8b for fast entity extraction (~100ms). Results are stored
    in the PostgreSQL entities table for the 'graph' query type in the
    cognitive engine.

    This is the LazyGraphRAG pattern: instead of building a full knowledge
    graph with a dedicated graph database, we use SQL aggregation over
    entity-document relationships stored in existing PostgreSQL.

    Cost: +1 Groq 8b call per document (~$0.0001). Zero query latency change.
    """
    import json

    try:
        from src.core.generation import fast_complete

        prompt = f"""Extract named entities from this text. Focus on: people, organizations, campaigns, clients, products, metrics, topics.
Reply JSON only: {{"entities": [{{"name": "entity name", "type": "person|org|campaign|client|product|metric|topic"}}]}}

Text: {text[:3000]}"""

        raw = await fast_complete(prompt, max_tokens=300, json_mode=True)
        parsed = json.loads(raw)
        entities = parsed.get("entities", [])

        if not entities:
            return

        # Upsert entities to PostgreSQL
        pool = await _get_pg()
        async with pool.acquire() as conn:
            for entity in entities[:20]:  # Cap at 20 entities per document
                name = entity.get("name", "").strip()
                etype = entity.get("type", "topic").strip()
                if not name:
                    continue

                # Upsert: increment mention_count and append doc_id to document_ids
                await conn.execute("""
                    INSERT INTO entities (tenant_id, entity_name, entity_type, document_ids, mention_count)
                    VALUES ($1, $2, $3, ARRAY[$4::uuid], 1)
                    ON CONFLICT (tenant_id, entity_name, entity_type)
                    DO UPDATE SET
                        document_ids = CASE
                            WHEN $4::uuid = ANY(entities.document_ids) THEN entities.document_ids
                            ELSE entities.document_ids || $4::uuid
                        END,
                        mention_count = entities.mention_count + 1,
                        updated_at = now()
                """, tenant_id, name, etype, doc_id)

    except Exception as e:
        _get_sanitize_logger().warning(
            f"[non-critical] Entity extraction failed for doc={doc_id}: {type(e).__name__}: {e}"
        )
