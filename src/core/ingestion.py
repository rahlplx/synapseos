"""
L1 — Ingestion Engine
Crawl4AI → Docling → SemanticChunker → SHA-256 dedup → sanitise → fastembed → Qdrant + MinIO + PG
ARM: Docling concurrency=1, batch_size=64 ingestion, OMP_NUM_THREADS=4
Security: Prompt injection sanitisation strips known injection patterns before embedding.
"""
import os
import asyncio
import hashlib
import io
import re as _re
import tempfile
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import models
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

from src.core.config import (
    INGEST_BATCH_SIZE, SCROLL_DELAY, COLLECTION_KNOWLEDGE,
    MINIO_RAW_BUCKET, MINIO_PARSED_BUCKET, RELEVANCE_GATE,
)
from src.core.clients import get_qdrant, get_keydb, get_minio
from src.core.db import get_pool

import logging
logger = logging.getLogger(__name__)

# ─── Models (shared with retrieval.py, lazy_load=True) ─────────────────────────
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)


# ─── MinIO Upload (unified) ────────────────────────────────────────────────────

async def upload_to_minio(bucket: str, content: bytes | str, object_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload content to MinIO. Accepts bytes or str (auto-encoded to UTF-8).
    Uses asyncio.to_thread to avoid blocking the event loop.
    Returns the object key.
    """
    client = get_minio()
    if isinstance(content, str):
        content = content.encode("utf-8")
        content_type = content_type or "text/markdown"
    data_stream = io.BytesIO(content)
    await asyncio.to_thread(
        client.put_object, bucket, object_key, data_stream, len(content),
        content_type=content_type,
    )
    return object_key


# ─── PostgreSQL Helpers (delegated to shared pool) ─────────────────────────────

async def upsert_document_record(
    tenant_id: str,
    source_url: Optional[str],
    source_filename: Optional[str],
    minio_raw_path: Optional[str],
    minio_parsed_path: Optional[str],
    chunk_count: int,
    status: str,
) -> str:
    """Insert a document record in PostgreSQL. Returns the document UUID."""
    doc_id = str(uuid4())
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, tenant_id, source_url, minio_raw_path, minio_parsed_path, chunk_count, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            doc_id, tenant_id, source_url, minio_raw_path, minio_parsed_path,
            chunk_count, status, datetime.now(timezone.utc),
        )
    return doc_id


async def update_document_status(doc_id: str, status: str, chunk_count: int = None):
    """Update document status and optionally chunk count in PostgreSQL."""
    pool = await get_pool()
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


async def log_interaction(tenant_id: str, event_type: str, detail: dict):
    """Write an interaction log to PostgreSQL after ingestion events."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interaction_logs (id, tenant_id, query, answer, contexts, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            str(uuid4()), tenant_id, f"[ingestion:{event_type}]",
                json.dumps(detail), json.dumps([]), datetime.now(timezone.utc),
        )


async def close_ingestion_clients():
    """Gracefully close async clients. Called on shutdown."""
    from src.core.db import close_pool
    await close_pool()


# ─── Core Pipeline ─────────────────────────────────────────────────────────────

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
        page_timeout=30000,
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
    Queue concurrency MUST be 1.
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
    """Split text into semantic chunks using semchunk + tiktoken (cl100k_base)."""
    from semchunk import chunk
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    chunks = chunk(text, chunk_size=max_tokens, token_counter=lambda t: len(enc.encode(t)))
    if not chunks:
        raise ValueError("Semantic chunking produced zero chunks — input may be too short")
    return chunks


# ─── Prompt Injection Sanitiser ────────────────────────────────────────────────

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

_injection_regex = _re.compile("|".join(INJECTION_PATTERNS), _re.IGNORECASE)


def sanitise_chunk(text: str, tenant_id: str = "") -> str | None:
    """Sanitise a chunk for prompt injection patterns.
    Returns None if the chunk contains a likely injection attempt (skip embedding).
    Returns cleaned text with HTML artifacts stripped if it passes.
    """
    if _injection_regex.search(text.lower()):
        logger.warning(
            f"[security] Prompt injection blocked for tenant={tenant_id}: {text[:100]}..."
        )
        return None

    # Strip HTML artifacts
    text = _re.sub(r'<script[^>]*>.*?</script>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<[^>]+>', '', text)
    return text.strip() or None


async def dedup_chunks(chunks: list[str], tenant_id: str) -> list[str]:
    """SHA-256 dedup — check KeyDB set per tenant."""
    keydb = get_keydb()
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
    Chunks are sanitised for prompt injection before embedding.
    """
    if not chunks:
        return

    # Sanitise chunks — skip any that contain prompt injection attempts
    clean_chunks = [c for c in chunks if sanitise_chunk(c, tenant_id) is not None]

    if not clean_chunks:
        logger.warning(f"[security] All chunks for tenant={tenant_id} blocked by sanitiser")
        return

    chunks = clean_chunks
    qdrant = get_qdrant()

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
    await qdrant.upsert(collection_name=COLLECTION_KNOWLEDGE, points=points)


# ─── Ingestion Entry Points ────────────────────────────────────────────────────

async def ingest_urls(
    urls: list[str],
    tenant_id: str,
    job_id: str,
    metadata: Optional[dict] = None,
):
    """Ingest a list of URLs: scrape → chunk → dedup → embed → upsert.
    Stores raw content in MinIO, writes document records to PostgreSQL.
    """
    keydb = get_keydb()
    metadata = metadata or {}
    await keydb.hset(f"job:{job_id}", mapping={"status": "processing", "total": len(urls), "done": 0})

    total_chunks = 0

    for url in urls:
        doc_id = None
        try:
            # 1. Scrape
            await keydb.hset(f"job:{job_id}", "current_url", url)
            markdown = await scrape_url(url)

            # 2. Store in MinIO
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
            raw_key = f"{tenant_id}/urls/{job_id}/{url_hash}.md"
            parsed_key = f"{tenant_id}/parsed/{job_id}/{url_hash}.md"
            await upload_to_minio(MINIO_RAW_BUCKET, markdown, raw_key)
            await upload_to_minio(MINIO_PARSED_BUCKET, markdown, parsed_key, "text/markdown")

            # 3. PostgreSQL document record
            doc_id = await upsert_document_record(
                tenant_id=tenant_id, source_url=url, source_filename=None,
                minio_raw_path=f"{MINIO_RAW_BUCKET}/{raw_key}",
                minio_parsed_path=f"{MINIO_PARSED_BUCKET}/{parsed_key}",
                chunk_count=0, status="processing",
            )

            # 4-5. Chunk + Dedup
            chunks = semantic_chunk(markdown)
            unique = await dedup_chunks(chunks, tenant_id)

            # 6. Embed + Upsert
            await embed_and_upsert(unique, tenant_id, {**metadata, "source_url": url})

            # 7. Update PostgreSQL
            await update_document_status(doc_id, "done", chunk_count=len(unique))

            # 8. Entity extraction (fire-and-forget)
            _fire_and_forget(_extract_and_store_entities(markdown, tenant_id, doc_id))

            # 9. Log ingestion event
            await log_interaction(
                tenant_id=tenant_id, event_type="url_ingest",
                detail={"job_id": job_id, "url": url, "doc_id": doc_id,
                         "chunk_count": len(unique), "minio_raw_path": f"{MINIO_RAW_BUCKET}/{raw_key}"},
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
    await keydb.expire(f"job:{job_id}", 86400)


async def ingest_file(
    file_bytes: bytes,
    filename: str,
    tenant_id: str,
    job_id: str,
):
    """Ingest an uploaded file: parse → chunk → dedup → embed → upsert."""
    keydb = get_keydb()
    doc_id = None
    await keydb.hset(f"job:{job_id}", "status", "processing")
    try:
        # 1. Store raw file in MinIO
        raw_key = f"{tenant_id}/files/{job_id}/{filename}"
        await upload_to_minio(MINIO_RAW_BUCKET, file_bytes, raw_key)

        # 2. Parse document
        markdown = parse_document(file_bytes, filename)

        # 3. Store parsed markdown in MinIO
        parsed_key = f"{tenant_id}/parsed/{job_id}/{filename}.md"
        await upload_to_minio(MINIO_PARSED_BUCKET, markdown, parsed_key, "text/markdown")

        # 4. PostgreSQL document record
        doc_id = await upsert_document_record(
            tenant_id=tenant_id, source_url=None, source_filename=filename,
            minio_raw_path=f"{MINIO_RAW_BUCKET}/{raw_key}",
            minio_parsed_path=f"{MINIO_PARSED_BUCKET}/{parsed_key}",
            chunk_count=0, status="processing",
        )

        # 5-6. Chunk + Dedup
        chunks = semantic_chunk(markdown)
        unique = await dedup_chunks(chunks, tenant_id)

        # 7. Embed + Upsert
        await embed_and_upsert(unique, tenant_id, {"source_filename": filename})

        # 8. Update PostgreSQL
        await update_document_status(doc_id, "done", chunk_count=len(unique))

        # 9. Entity extraction (fire-and-forget)
        _fire_and_forget(_extract_and_store_entities(markdown, tenant_id, doc_id))

        # 10. Log ingestion event
        await log_interaction(
            tenant_id=tenant_id, event_type="file_ingest",
            detail={"job_id": job_id, "filename": filename, "doc_id": doc_id,
                     "chunk_count": len(unique), "minio_raw_path": f"{MINIO_RAW_BUCKET}/{raw_key}"},
        )

        await keydb.hset(f"job:{job_id}", mapping={"status": "done", "chunk_count": len(unique)})
    except Exception as e:
        if doc_id:
            await update_document_status(doc_id, "failed")
        await keydb.hset(f"job:{job_id}", mapping={"status": "failed", "error": str(e)[:500]})

    await keydb.expire(f"job:{job_id}", 86400)


# ─── Fire-and-Forget Task Tracking ─────────────────────────────────────────────
# Prevents tasks from being silently lost during shutdown.

_tracked_tasks: set = set()


def _fire_and_forget(coro):
    """Schedule a coroutine as a background task with done callback for cleanup."""
    task = asyncio.create_task(coro)
    _tracked_tasks.add(task)
    task.add_done_callback(_tracked_tasks.discard)


async def drain_tracked_tasks(timeout: float = 5.0):
    """Wait for all tracked background tasks to complete. Called on shutdown."""
    if not _tracked_tasks:
        return
    await asyncio.wait(_tracked_tasks, timeout=timeout)


# ─── Entity Extraction (LazyGraphRAG) ───────────────────────────────────────

async def _extract_and_store_entities(text: str, tenant_id: str, doc_id: str):
    """Extract named entities from text and upsert to entities table.
    Uses Groq 8b for fast extraction (~100ms). Fire-and-forget — never blocks ingestion.
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

        pool = await get_pool()
        async with pool.acquire() as conn:
            for entity in entities[:20]:
                name = entity.get("name", "").strip()
                etype = entity.get("type", "topic").strip()
                if not name:
                    continue
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
        logger.warning(f"[non-critical] Entity extraction failed for doc={doc_id}: {type(e).__name__}: {e}")
