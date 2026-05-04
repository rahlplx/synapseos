# SynapseOS — GitHub Copilot Instructions

## Project
Self-improving BYOK RAG platform. Oracle ARM (4 vCPU / 24GB, no GPU).

## Stack (locked)
FastAPI | Qdrant | fastembed bge-base-en-v1.5 768d | LiteLLM/Groq |
mem0ai | Crawl4AI | Docling | RAGAS | DSPy | Langfuse | KeyDB | MinIO

## Rules
- OMP_NUM_THREADS=4 before fastembed
- batch_size 64 ingest / 16 query
- max 15 docs to cross-encoder
- KeyDB: AOF only (save "")
- Qdrant: on_disk=True
- tenant_id filter on every Qdrant query
- Fernet encryption for BYOK keys
- All async — no sync blocking
- Groq primary LLM (groq/llama-3.1-70b-versatile for generation, 8b for fast tasks)
- Complete file output — no partial code
