"""
Proxy chat → OpenWebUI.
Le modèle personnalisé (avec tool stravbike_tool.py rattaché) vit côté OpenWebUI.
Ce routeur forward les messages du frontend vers l'API OpenWebUI et stream la réponse.

Trois éléments indispensables dans le payload pour reproduire le comportement natif :
1. tool_ids       → OpenWebUI résout specs + callables, injecte `tools` au format OpenAI
2. chat_id + id   → active event_emitter → prend le handler streaming complet avec boucle
                     tool_call → exécution → second appel LLM (sinon: fallback sans boucle)
3. stream: True   → la boucle d'exécution n'existe que dans le handler streaming

chat_id préfixé "local:" → skip des écritures DB (pas de chat persistant côté OpenWebUI).

⚠️ DIAGNOSTIC : logging détaillé de chaque ligne SSE reçue d'OpenWebUI.
    À réduire après analyse.
"""
import os
import json
import uuid
import logging
import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from api.dependencies import verify_service_key

load_dotenv()

logger = logging.getLogger("stravbike.chat_proxy")
logging.basicConfig(level=logging.DEBUG)

router = APIRouter()

OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "")
OPENWEBUI_TOOL_IDS = [
    tid.strip()
    for tid in os.getenv("OPENWEBUI_TOOL_IDS", "").split(",")
    if tid.strip()
]


class ChatMessage(BaseModel):
    message: str


@router.post("/")
async def chat_endpoint(msg: ChatMessage):
    """Proxy streaming vers OpenWebUI (modèle + tool stravbike)."""

    # Vérifier que la config est en place
    if not OPENWEBUI_API_KEY:
        return JSONResponse(
            {"error": "OPENWEBUI_API_KEY non configuré dans .env"},
            status_code=503,
        )
    if not OPENWEBUI_MODEL:
        return JSONResponse(
            {"error": "OPENWEBUI_MODEL non configuré dans .env"},
            status_code=503,
        )
    if not OPENWEBUI_TOOL_IDS:
        return JSONResponse(
            {"error": "OPENWEBUI_TOOL_IDS non configuré dans .env"},
            status_code=503,
        )

    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json",
    }

    # chat_id préfixé "local:" → event_emitter activé mais écritures DB skipées
    # id (message_id) → requis avec chat_id pour que event_emitter soit non-None
    chat_id = f"local:{uuid.uuid4()}"
    message_id = str(uuid.uuid4())

    payload = {
        "model": OPENWEBUI_MODEL,
        "messages": [{"role": "user", "content": msg.message}],
        "stream": True,
        "tool_ids": OPENWEBUI_TOOL_IDS,
        "chat_id": chat_id,
        "id": message_id,
    }

    logger.info("===== PROXY CHAT REQUEST =====")
    logger.info("  message: %s", msg.message)
    logger.info("  chat_id: %s", chat_id)
    logger.info("  message_id: %s", message_id)
    logger.info("  tool_ids: %s", OPENWEBUI_TOOL_IDS)
    logger.info("  model: %s", OPENWEBUI_MODEL)
    logger.info("  url: %s/api/chat/completions", OPENWEBUI_BASE_URL)

    line_count = 0
    content_chunks_sent = 0
    tool_call_chunks_seen = 0
    done_markers_seen = 0

    async def event_stream():
        nonlocal line_count, content_chunks_sent, tool_call_chunks_seen, done_markers_seen
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{OPENWEBUI_BASE_URL}/api/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                ) as resp:
                    logger.info("  HTTP status: %s", resp.status_code)
                    logger.info("  response headers: %s", dict(resp.headers))

                    if resp.status_code != 200:
                        body = await resp.aread()
                        logger.error("  ERROR body: %s", body.decode('utf-8', 'replace'))
                        yield f"data: {json.dumps({'error': f'OpenWebUI returned {resp.status_code}'})}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        line_count += 1

                        # Log EVERY raw line (truncated to 500 chars)
                        raw_preview = line[:500]
                        logger.debug("  [line %d] raw: %s", line_count, raw_preview)

                        # Log non-SSE lines (could be errors, blank lines, etc.)
                        if not line.startswith("data: "):
                            if line.strip():
                                logger.warning("  [line %d] non-SSE content: %s", line_count, raw_preview)
                            continue

                        data = line[6:]

                        if data.strip() == "[DONE]":
                            done_markers_seen += 1
                            logger.info("  [line %d] [DONE] marker (count=%d)", line_count, done_markers_seen)
                            yield "data: [DONE]\n\n"
                            break

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            logger.warning("  [line %d] JSON decode failed: %s", line_count, data[:200])
                            continue

                        # Log the full chunk structure (keys, finish_reason, tool_calls)
                        choices = chunk.get("choices", [])
                        if choices:
                            choice = choices[0]
                            delta = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")

                            # Log finish_reason
                            if finish_reason:
                                logger.info("  [line %d] finish_reason: %s", line_count, finish_reason)

                            # Log tool_calls in delta
                            delta_tool_calls = delta.get("tool_calls")
                            if delta_tool_calls:
                                tool_call_chunks_seen += 1
                                logger.info("  [line %d] delta.tool_calls: %s",
                                            line_count, json.dumps(delta_tool_calls, ensure_ascii=False)[:500])

                            # Log content
                            content = delta.get("content", "")
                            if content:
                                content_chunks_sent += 1
                                if content_chunks_sent <= 3:
                                    logger.info("  [line %d] delta.content (first chunks): %s",
                                                line_count, content[:200])
                                yield f"data: {json.dumps({'content': content})}\n\n"

                            # Log reasoning if present
                            reasoning = delta.get("reasoning")
                            if reasoning:
                                logger.debug("  [line %d] delta.reasoning: %s", line_count, reasoning[:200])

                        # Log non-choices structure (e.g. OpenWebUI event objects)
                        if not choices:
                            logger.info("  [line %d] non-choices chunk keys: %s",
                                        line_count, list(chunk.keys()))

                    logger.info("===== PROXY CHAT SUMMARY =====")
                    logger.info("  total lines: %d", line_count)
                    logger.info("  content chunks sent: %d", content_chunks_sent)
                    logger.info("  tool_call chunks seen: %d", tool_call_chunks_seen)
                    logger.info("  [DONE] markers: %d", done_markers_seen)
                    logger.info("===== END SUMMARY =====")

        except httpx.ConnectError:
            logger.error("ConnectError to %s", OPENWEBUI_BASE_URL)
            yield f"data: {json.dumps({'error': f'Impossible de joindre OpenWebUI ({OPENWEBUI_BASE_URL}). Vérifiez OPENWEBUI_BASE_URL et que le service tourne.'})}\n\n"
        except Exception as e:
            logger.exception("Unexpected error in event_stream")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
