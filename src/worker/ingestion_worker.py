"""KeyDB job queue consumer — processes ingestion jobs sequentially (concurrency=1)."""
import asyncio, os
import redis.asyncio as redis

keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))

async def process_queue():
    print("Ingestion worker started — waiting for jobs...")
    while True:
        job = await keydb.brpop("ingestion_queue", timeout=5)
        if job:
            _, job_id = job
            print(f"Processing job: {job_id.decode()}")
            # Jobs are processed via FastAPI BackgroundTasks in Phase 1
            # This worker handles overflow queue in Phase 2
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(process_queue())
