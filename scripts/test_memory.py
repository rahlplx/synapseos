"""
SynapseOS — Memory Test
Proves memory persists ACROSS separate session IDs (not just same context).
Run: python3 scripts/test_memory.py
Requires: Qdrant running, mem0ai installed, GROQ_API_KEY set
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("KEYDB_URL", "redis://localhost:6379")

import asyncio
from src.cognitive.memory import load_memories, write_memory, load_session, append_session


async def main():
    print("=== SynapseOS — Memory Test ===\n")
    user_id = "rahul"
    tenant_id = "test"

    # Step 1: Store a memory
    print("Step 1: Storing memory...")
    messages = [
        {"role": "user", "content": "My name is Rahul. I run a digital marketing agency in Bangladesh called SR Creative Hub."},
        {"role": "assistant", "content": "Got it! I'll remember that you're Rahul, running SR Creative Hub in Bangladesh."},
    ]
    await write_memory(user_id, tenant_id, messages)
    print("  Memory written. Facts stored by mem0.")
    await asyncio.sleep(2)  # Wait for async memory write to complete

    # Step 2: Recall in different session
    print("\nStep 2: Recalling memory in different session...")
    session_id = "totally-new-session-xyz"
    question = "What is my name and what business do I run?"
    memories = await load_memories(user_id, tenant_id, question)
    print(f"  Memories recalled: {memories}")
    recalled = "Rahul" in memories
    print(f"  {'✅ PASS: memory recalled across sessions' if recalled else '❌ FAIL: no memory recalled'}")

    # Step 3: Test session storage
    print("\nStep 3: Testing session storage...")
    await append_session(session_id, "user", "Hello, testing session")
    await append_session(session_id, "assistant", "Session test confirmed")
    turns = await load_session(session_id)
    session_ok = len(turns) > 0
    print(f"  Session turns loaded: {len(turns)}")
    print(f"  {'✅ PASS' if session_ok else '❌ FAIL'}")

    # Step 4: Verify in Qdrant
    print("\nStep 4: Verifying in Qdrant...")
    from qdrant_client import AsyncQdrantClient
    client = AsyncQdrantClient(url=os.environ["QDRANT_URL"])
    try:
        info = await client.get_collection("synapse_memory")
        print(f"  Vectors in synapse_memory: {info.vectors_count}")
    except Exception as e:
        print(f"  Could not read synapse_memory: {e}")
    await client.close()

    results = [recalled, session_ok]
    print(f"\n=== Final: {sum(results)}/2 tests passed ===")


if __name__ == "__main__":
    asyncio.run(main())
