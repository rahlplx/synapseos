"""
L1 — Ingestion Engine
Crawl4AI → Docling → SemanticChunker → SHA-256 dedup → fastembed → Qdrant + MinIO + PG
ARM: Docling concurrency=1, batch_size=64
"""
import os, hashlib
from uuid import uuid4
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import AsyncQdrantClient, models
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
import redis.asyncio as redis

qdrant = AsyncQdrantClient(url=os.environ.get("QDRANT_URL", "http://qdrant:6333"))
keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)
COLLECTION = "synapse_knowledge"


async def scrape_url(url: str) -> str:
    md_gen = DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=0.48))
    config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, markdown_generator=md_gen, page_timeout=30000, scan_full_page=True)
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        return result.markdown.fit_markdown


def parse_document(file_bytes: bytes, filename: str) -> str:
    import tempfile, os
    from docling.document_converter import DocumentConverter
    suffix = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        tmp_path = f.name
    try:
        converter = DocumentConverter()
        doc = converter.convert(source=f"file://{tmp_path}")
        return doc.export_to_markdown()
    finally:
        os.unlink(tmp_path)


def semantic_chunk(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    from semchunk import SemanticChunker
    chunker = SemanticChunker(tokenizer="BAAI/bge-base-en-v1.5", chunk_size=max_tokens, overlap=overlap)
    return chunker.chunk_text(text)


async def embed_and_upsert(chunks: list[str], tenant_id: str, metadata: dict):
    if not chunks:
        return
    dense_vecs = list(dense_model.embed(chunks, batch_size=64))
    sparse_vecs = list(sparse_model.embed(chunks, batch_size=64))
    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector={"dense": dense_vecs[i].tolist(), "sparse": sparse_vecs[i].as_object()},
            payload={"text": chunks[i], "tenant_id": tenant_id, **metadata},
        )
        for i in range(len(chunks))
    ]
    await qdrant.upsert(collection_name=COLLECTION, points=points)


async def dedup_chunks(chunks: list[str], tenant_id: str) -> list[str]:
    unique = []
    for chunk in chunks:
        h = hashlib.sha256(chunk.encode()).hexdigest()
        added = await keydb.sadd(f"tenant:{tenant_id}:hashes", h)
        if added:
            unique.append(chunk)
    return unique


async def ingest_urls(urls: list[str], tenant_id: str, job_id: str, metadata: dict = {}):
    await keydb.hset(f"job:{job_id}", "status", "processing")
    for url in urls:
        try:
            markdown = await scrape_url(url)
            chunks = semantic_chunk(markdown)
            unique = await dedup_chunks(chunks, tenant_id)
            await embed_and_upsert(unique, tenant_id, {**metadata, "source_url": url})
        except Exception as e:
            await keydb.hset(f"job:{job_id}", "error", str(e))
    await keydb.hset(f"job:{job_id}", "status", "done")


async def ingest_file(file_bytes: bytes, filename: str, tenant_id: str, job_id: str):
    await keydb.hset(f"job:{job_id}", "status", "processing")
    try:
        markdown = parse_document(file_bytes, filename)
        chunks = semantic_chunk(markdown)
        unique = await dedup_chunks(chunks, tenant_id)
        await embed_and_upsert(unique, tenant_id, {"source_filename": filename})
        await keydb.hset(f"job:{job_id}", "status", "done")
    except Exception as e:
        await keydb.hset(f"job:{job_id}", "status", "failed")
        await keydb.hset(f"job:{job_id}", "error", str(e))
