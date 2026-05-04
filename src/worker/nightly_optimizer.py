"""
L4 — Nightly Intelligence Loop
02:00 UTC: RAGAS score logs → SFT/DPO JSONL export → DSPy MIPROv2 optimization
"""
import asyncio
import json
import os
from datetime import datetime
from io import BytesIO

import boto3
import dspy
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from datasets import Dataset
from apscheduler.schedulers.asyncio import AsyncIOScheduler

minio = boto3.client(
    "s3",
    endpoint_url=f"http://{os.environ.get('MINIO_ENDPOINT', 'minio:9000')}",
    aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY"),
)

# Ensure MinIO bucket exists
try:
    minio.head_bucket(Bucket="synapseos")
except Exception:
    try:
        minio.create_bucket(Bucket="synapseos")
    except Exception:
        pass


async def score_unscored_logs():
    """Run RAGAS evaluation on unscored interaction logs."""
    import asyncpg

    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch("""
            SELECT id, query, answer, contexts
            FROM interaction_logs
            WHERE ragas_combined IS NULL
              AND answer != ''
            LIMIT 50
        """)

        if not rows:
            print("No unscored logs — skipping RAGAS")
            return []

        for row in rows:
            try:
                dataset = Dataset.from_list([{
                    "question": row["query"],
                    "answer": row["answer"],
                    "contexts": row["contexts"] if isinstance(row["contexts"], list) else [],
                }])

                result = evaluate(
                    dataset=dataset,
                    metrics=[faithfulness, answer_relevancy, context_precision],
                )

                combined = (
                    0.4 * result["faithfulness"]
                    + 0.3 * result["answer_relevancy"]
                    + 0.3 * result["context_precision"]
                )

                await conn.execute("""
                    UPDATE interaction_logs
                    SET ragas_faithfulness=$2, ragas_relevancy=$3,
                        ragas_precision=$4, ragas_combined=$5
                    WHERE id=$1::uuid
                """, row["id"],
                    float(result["faithfulness"]),
                    float(result["answer_relevancy"]),
                    float(result["context_precision"]),
                    float(combined),
                )
            except Exception as e:
                print(f"RAGAS scoring failed for log {row['id']}: {e}")

        return rows
    finally:
        await conn.close()


async def export_datasets(version: str = None):
    """Export SFT + DPO datasets to MinIO in ChatML format."""
    import asyncpg

    if not version:
        version = f"v{datetime.utcnow().strftime('%Y%m%d')}"

    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    conn = await asyncpg.connect(db_url)
    try:
        # SFT: combined >= 0.7, all dimensions >= 0.6
        sft_rows = await conn.fetch("""
            SELECT query, answer FROM interaction_logs
            WHERE ragas_combined >= 0.7
              AND ragas_faithfulness >= 0.6
              AND ragas_relevancy >= 0.6
              AND dataset_exported = FALSE
        """)

        # DPO: pair best vs worst answer for same query
        # Use a subquery because HAVING is invalid with DISTINCT ON in PostgreSQL.
        dpo_rows = await conn.fetch("""
            SELECT sub.query, sub.chosen, sub.rejected
            FROM (
                SELECT DISTINCT ON (query)
                    query,
                    first_value(answer) OVER w AS chosen,
                    last_value(answer) OVER w AS rejected,
                    max(ragas_combined) OVER w AS max_score,
                    min(ragas_combined) OVER w AS min_score
                FROM interaction_logs
                WHERE ragas_combined IS NOT NULL
                WINDOW w AS (PARTITION BY query ORDER BY ragas_combined
                             ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            ) sub
            WHERE sub.max_score >= 0.7 AND sub.min_score <= 0.4
        """)

        # Mark as exported
        await conn.execute("""
            UPDATE interaction_logs SET dataset_exported = TRUE
            WHERE ragas_combined >= 0.7 AND dataset_exported = FALSE
        """)

    finally:
        await conn.close()

    # SFT — ChatML format (Qwen3 / Unsloth compatible)
    sft_lines = []
    for row in sft_rows:
        sft_lines.append(json.dumps({
            "messages": [
                {"role": "system", "content": "You are a precise knowledge assistant."},
                {"role": "user", "content": row["query"]},
                {"role": "assistant", "content": row["answer"]},
            ]
        }))

    # DPO — ChatML format
    dpo_lines = []
    for row in dpo_rows:
        dpo_lines.append(json.dumps({
            "prompt": [
                {"role": "system", "content": "You are a precise knowledge assistant."},
                {"role": "user", "content": row["query"]},
            ],
            "chosen": [{"role": "assistant", "content": row["chosen"]}],
            "rejected": [{"role": "assistant", "content": row["rejected"]}],
        }))

    # Upload to MinIO
    for key, lines in [
        (f"datasets/{version}/sft_train.jsonl", sft_lines),
        (f"datasets/{version}/dpo_train.jsonl", dpo_lines),
    ]:
        if lines:
            data = "\n".join(lines).encode()
            minio.put_object(
                "synapseos", key, BytesIO(data), len(data),
                content_type="application/x-ndjson",
            )

    print(f"Exported: SFT={len(sft_lines)} pairs, DPO={len(dpo_lines)} pairs to {version}")


async def run_dspy_optimization():
    """DSPy MIPROv2 nightly prompt optimization.
    Only runs if there are enough high-quality examples (>= 10).
    """
    import asyncpg

    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    conn = await asyncpg.connect(db_url)
    try:
        gold_logs = await conn.fetch("""
            SELECT query, answer, contexts FROM interaction_logs
            WHERE ragas_combined >= 0.85
            ORDER BY created_at DESC LIMIT 100
        """)
    finally:
        await conn.close()

    if len(gold_logs) < 10:
        print("Insufficient gold examples for DSPy optimization — skipping")
        return

    trainset = [
        dspy.Example(
            question=log["query"],
            context="\n".join(log["contexts"]) if isinstance(log["contexts"], list) else str(log["contexts"]),
            answer=log["answer"],
        ).with_inputs("question", "context")
        for log in gold_logs
    ]

    class SynapseRAG(dspy.Module):
        def __init__(self):
            super().__init__()
            self.generate = dspy.ChainOfThought("context, question -> answer")

        def forward(self, question, context):
            return self.generate(context=context, question=question)

    optimizer = dspy.MIPROv2(
        metric=dspy.evaluate.SemanticF1(),
        auto="light",
        num_threads=4,
        max_bootstrapped_demos=3,
        max_labeled_demos=3,
    )

    optimized = optimizer.compile(SynapseRAG(), trainset=trainset, num_trials=25)
    optimized.save("optimized_prompt.json")
    print("DSPy MIPROv2 optimization complete")


async def score_and_export():
    """Nightly job: RAGAS score → JSONL export → DSPy optimization."""
    print(f"[{datetime.utcnow()}] Nightly optimization starting...")
    try:
        await score_unscored_logs()
        await export_datasets()
        await run_dspy_optimization()
    except Exception as e:
        print(f"Nightly optimization error: {e}")
    print(f"[{datetime.utcnow()}] Nightly optimization complete")


def start_scheduler():
    """Start the APScheduler for nightly runs at 02:00 UTC."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: asyncio.ensure_future(score_and_export()),
        "cron",
        hour=2,
        minute=0,
        timezone="UTC",
    )
    scheduler.start()
    return scheduler
