"""KeyDB job queue consumer — processes ingestion jobs sequentially (concurrency=1).
This worker handles overflow from FastAPI BackgroundTasks and ensures
Docling never runs with concurrency > 1 on ARM.
"""
import asyncio
import json
import logging
import os
import redis.asyncio as redis

from src.core.ingestion import ingest_urls, ingest_file

logger = logging.getLogger(__name__)

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))


async def process_queue():
    """Process ingestion jobs from the KeyDB queue.
    Uses BRPOP for efficient blocking wait. Sequential processing (concurrency=1).
    """
    print("Ingestion worker started — waiting for jobs (concurrency=1)...")

    while True:
        try:
            # Block until a job is available (timeout=5s for clean shutdown)
            job = await keydb.brpop("ingestion_queue", timeout=5)
            if not job:
                continue

            _, job_data = job
            data = json.loads(job_data)

            job_id = data["job_id"]
            tenant_id = data["tenant_id"]
            job_type = data.get("type", "urls")

            print(f"Processing job: {job_id} (type={job_type})")

            if job_type == "urls":
                await ingest_urls(
                    urls=data["urls"],
                    tenant_id=tenant_id,
                    job_id=job_id,
                    metadata=data.get("metadata", {}),
                )
            elif job_type == "file":
                await ingest_file(
                    file_bytes=data["file_bytes"],
                    filename=data["filename"],
                    tenant_id=tenant_id,
                    job_id=job_id,
                )

            print(f"Job {job_id} complete")

        except json.JSONDecodeError as e:
            print(f"Invalid job data: {e}")
        except Exception as e:
            print(f"Job processing error: {e}")
            try:
                await keydb.hset(f"job:{job_id}", mapping={"status": "failed", "error": str(e)[:500]})
            except Exception as e2:
                logger.error(f"[critical] Failed to write failure status for job {job_id}: {type(e2).__name__}: {e2}")


if __name__ == "__main__":
    asyncio.run(process_queue())
