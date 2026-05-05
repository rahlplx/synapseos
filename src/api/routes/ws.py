"""WebSocket endpoint for real-time cognitive thinking.

WS /v1/ws/think — Full cognitive engine over WebSocket.
Enables bidirectional communication: client sends questions, server streams
reasoning steps, tool calls, and final answer in real-time.

Protocol:
  Client → Server: {"type": "think", "question": "...", "session_id": "...", "user_id": "..."}
  Server → Client: {"type": "step", "step": "classifying", ...}
  Server → Client: {"type": "step", "step": "retrieving", ...}
  Server → Client: {"type": "chunk", "text": "..."}
  Server → Client: {"type": "done", "answer": "...", "query_type": "...", ...}
  Server → Client: {"type": "error", "message": "..."}
"""
import json
import logging
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.models import _latency_ms
from src.cognitive.engine import cognitive_query
from src.cognitive.planner import classify_query
from src.cognitive.memory import load_session, load_memories
from src.core.retrieval import hybrid_query_with_retry
from src.core.generation import generate_stream
from src.core.ingestion import _fire_and_forget
from src.cognitive.memory import write_memory, append_session

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/think")
async def ws_think(websocket: WebSocket):
    """WebSocket endpoint for real-time cognitive queries.

    Auth: Client must send X-Tenant-ID and X-API-Key headers during handshake.
    Protocol is JSON-based: client sends think requests, server streams steps and answer.
    """
    # ── Auth via query params (WS doesn't support custom headers easily) ──
    tenant_id = websocket.query_params.get("tenant_id")
    api_key = websocket.query_params.get("api_key")

    if not tenant_id:
        await websocket.close(code=4001, reason="Missing tenant_id query parameter")
        return

    await websocket.accept()

    try:
        while True:
            # ── Receive request ──
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if msg.get("type") != "think":
                await websocket.send_json({"type": "error", "message": "Expected type 'think'"})
                continue

            question = msg.get("question", "")
            session_id = msg.get("session_id", "ws-default")
            user_id = msg.get("user_id", "ws-user")

            if not question:
                await websocket.send_json({"type": "error", "message": "Missing 'question'"})
                continue

            start = time.perf_counter()

            try:
                # ── Step 1: Classify ──
                await websocket.send_json({"type": "step", "step": "classifying"})
                query_type = await classify_query(question)
                await websocket.send_json({"type": "classified", "query_type": query_type})

                # ── Step 2: Retrieve ──
                await websocket.send_json({"type": "step", "step": "retrieving"})
                hits, confidence = await hybrid_query_with_retry(question, tenant_id)
                contexts = [h.payload.get("text", "") for h in hits]
                await websocket.send_json({
                    "type": "retrieved",
                    "contexts_count": len(contexts),
                    "confidence": confidence,
                })

                # ── Step 3: Stream generation ──
                await websocket.send_json({"type": "step", "step": "generating"})
                full_answer = ""
                async for chunk_bytes in generate_stream(question, contexts, api_key):
                    try:
                        chunk_raw = chunk_bytes.replace("data: ", "").strip()
                        payload = json.loads(chunk_raw)
                        if "chunk" in payload:
                            full_answer += payload["chunk"]
                            await websocket.send_json({"type": "chunk", "text": payload["chunk"]})
                    except Exception:
                        pass

                # ── Step 4: Reflect ──
                await websocket.send_json({"type": "step", "step": "reflecting"})
                from src.cognitive.reflection import reflect_and_refine
                context_str = "\n\n---\n\n".join(contexts)
                final_answer, scores = await reflect_and_refine(
                    question=question, context=context_str, answer=full_answer,
                )

                # ── Step 5: Memory write (fire-and-forget) ──
                messages = [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": final_answer},
                ]
                _fire_and_forget(write_memory(user_id, tenant_id, messages))
                _fire_and_forget(append_session(session_id, "user", question))
                _fire_and_forget(append_session(session_id, "assistant", final_answer))

                # ── Done ──
                await websocket.send_json({
                    "type": "done",
                    "answer": final_answer,
                    "query_type": query_type,
                    "confidence": confidence,
                    "reflection_scores": scores,
                    "latency_ms": _latency_ms(start),
                })

            except Exception as e:
                logger.error(f"[ws] Error processing think: {type(e).__name__}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"{type(e).__name__}: {str(e)[:200]}",
                })

    except WebSocketDisconnect:
        logger.debug("[ws] Client disconnected")
    except Exception as e:
        logger.error(f"[ws] Unexpected error: {type(e).__name__}: {e}")
