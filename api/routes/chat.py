"""
Proxy chat → OpenWebUI avec boucle tool_call native + mémoire de conversation.

Architecture :
  1. Le frontend envoie l'historique complet de la conversation (messages[]).
  2. Le proxy forward cet historique à OpenWebUI AVEC tool_ids mais SANS chat_id/id.
     → event_emitter = None → fallback streaming path → raw LLM SSE transmis tel quel.
  3. Le proxy stream le contenu + reasoning au frontend en temps réel (SSE).
  4. Le proxy collecte les tool_calls dans le flux SSE.
  5. Quand le stream se termine avec finish_reason="tool_calls", le proxy exécute
     les tools localement (appels HTTP vers l'API stravbike).
  6. Le proxy construit un nouveau messages avec les résultats et renvoie à OpenWebUI.
  7. Le proxy stream la nouvelle réponse. Boucle jusqu'à finish_reason="stop".
"""
import os
import json
import logging
import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from api.dependencies import verify_service_key

load_dotenv()

logger = logging.getLogger("stravbike.chat_proxy")

router = APIRouter()

OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "")
OPENWEBUI_TOOL_IDS = [
    tid.strip()
    for tid in os.getenv("OPENWEBUI_TOOL_IDS", "").split(",")
    if tid.strip()
]

# Clé de service pour appeler l'API stravbike (même que l'outil OpenWebUI)
STRAVBIKE_SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY", "")
STRAVBIKE_API_BASE = os.getenv("STRAVBIKE_API_BASE", "http://localhost:2024/api")

# Nombre max d'itérations tool_call (sécurité)
MAX_TOOL_ITERATIONS = 5


class ChatRequest(BaseModel):
    """Accepte soit un message simple (legacy) soit un historique complet."""
    message: Optional[str] = None
    messages: Optional[list[dict]] = None


# ── Mapping tool → endpoint stravbike ─────────────────────────────────

async def execute_tool(function_name: str, arguments: dict) -> str:
    """Exécute un tool stravbike en appellant l'API locale."""
    headers = {"X-API-Key": STRAVBIKE_SERVICE_KEY}

    async with httpx.AsyncClient() as client:
        if function_name == "get_athlete_profile":
            resp = await client.get(f"{STRAVBIKE_API_BASE}/athlete", headers=headers, timeout=10)
            return resp.text

        elif function_name == "get_week_calendar":
            resp = await client.get(
                f"{STRAVBIKE_API_BASE}/calendar/week",
                params={"start_date": arguments.get("start_date", "")},
                headers=headers,
                timeout=10,
            )
            return resp.text

        elif function_name == "get_activity_detail":
            resp = await client.get(
                f"{STRAVBIKE_API_BASE}/activities/{arguments.get('activity_id', '')}",
                headers=headers,
                timeout=10,
            )
            return resp.text

        elif function_name == "get_competitions":
            resp = await client.get(f"{STRAVBIKE_API_BASE}/competitions/", headers=headers, timeout=10)
            return resp.text

        elif function_name == "get_planned_sessions":
            resp = await client.get(
                f"{STRAVBIKE_API_BASE}/sessions/",
                params={"week": arguments.get("week", "")},
                headers=headers,
                timeout=10,
            )
            return resp.text

        elif function_name == "add_coach_comment":
            resp = await client.post(
                f"{STRAVBIKE_API_BASE}/comments",
                json={
                    "activity_id": arguments.get("activity_id"),
                    "comment": arguments.get("comment", ""),
                },
                headers=headers,
                timeout=30,
            )
            return resp.text

        elif function_name == "sync_latest_activities":
            resp = await client.post(
                f"{STRAVBIKE_API_BASE}/activities/refresh",
                headers=headers,
                timeout=30,
            )
            return resp.text

        else:
            return f"Erreur: tool '{function_name}' non reconnu par le proxy."


# ── Helper : stream une requête OpenWebUI et forward au frontend ──────

async def stream_openwebui_response(
    client: httpx.AsyncClient,
    payload: dict,
    headers: dict,
):
    """
    Envoie une requête streaming à OpenWebUI et yield les events SSE.

    Yields:
        ("content", text)       — contenu à forwarder au frontend
        ("reasoning", text)     — reasoning à forwarder au frontend
        ("tool_call", chunk)    — chunk contenant tool_calls (à collecter)
        ("finish", reason)      — finish_reason du stream
        ("done",)               — stream terminé ([DONE])
        ("error", message)      — erreur

    Stocke l'assistant message complet dans les attributs de la fonction.
    """
    accumulated_content = ""
    accumulated_reasoning = ""
    tool_calls_acc = {}  # index → {"id": ..., "function": {"name": ..., "arguments": ""}}
    finish_reason = None

    async with client.stream(
        "POST",
        f"{OPENWEBUI_BASE_URL}/api/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    ) as resp:
        logger.info("  HTTP status: %s", resp.status_code)

        if resp.status_code != 200:
            body = await resp.aread()
            err = body.decode("utf-8", "replace")
            logger.error("  ERROR body: %s", err[:500])
            yield ("error", f"OpenWebUI returned {resp.status_code}: {err[:200]}")
            return

        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue

            data = line[6:].strip()

            if data == "[DONE]":
                yield ("done",)
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("  JSON decode failed: %s", data[:200])
                continue

            choices = chunk.get("choices", [])
            if not choices:
                logger.debug("  non-choices chunk: %s", list(chunk.keys()))
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            fr = choice.get("finish_reason")

            # Content
            content = delta.get("content", "")
            if content:
                accumulated_content += content
                yield ("content", content)

            # Reasoning
            reasoning = delta.get("reasoning", "")
            if reasoning:
                accumulated_reasoning += reasoning
                yield ("reasoning", reasoning)

            # Tool calls
            delta_tc = delta.get("tool_calls")
            if delta_tc:
                for tc in delta_tc:
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        tool_calls_acc[idx]["function"]["name"] = fn["name"]
                    if fn.get("arguments"):
                        tool_calls_acc[idx]["function"]["arguments"] += fn["arguments"]
                yield ("tool_call", delta_tc)

            # Finish reason
            if fr:
                finish_reason = fr
                logger.info("  finish_reason: %s", fr)

    # Construire l'assistant message pour le prochain tour
    assistant_msg = {"role": "assistant", "content": accumulated_content or ""}
    if accumulated_reasoning:
        assistant_msg["reasoning"] = accumulated_reasoning
    if tool_calls_acc:
        assistant_msg["tool_calls"] = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]

    # Stocker pour le caller via attributs de fonction
    stream_openwebui_response._last_assistant_msg = assistant_msg
    stream_openwebui_response._last_finish_reason = finish_reason


# ── Endpoint principal ────────────────────────────────────────────────

@router.post("/")
async def chat_endpoint(req: ChatRequest):
    """Proxy streaming vers OpenWebUI avec boucle tool_call native + mémoire."""

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

    # Construire les messages : historique fourni ou message simple (legacy)
    if req.messages:
        messages = req.messages
    elif req.message:
        messages = [{"role": "user", "content": req.message}]
    else:
        return JSONResponse(
            {"error": "Aucun message fourni (ni 'message' ni 'messages')"},
            status_code=400,
        )

    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Payload de base (sans chat_id/id → fallback streaming path)
    base_payload = {
        "model": OPENWEBUI_MODEL,
        "stream": True,
        "tool_ids": OPENWEBUI_TOOL_IDS,
    }

    logger.info("===== PROXY CHAT REQUEST =====")
    logger.info("  messages count: %d", len(messages))
    logger.info("  tool_ids: %s", OPENWEBUI_TOOL_IDS)
    logger.info("  model: %s", OPENWEBUI_MODEL)

    async def event_stream():
        iteration = 0
        try:
            async with httpx.AsyncClient() as client:
                while iteration < MAX_TOOL_ITERATIONS:
                    iteration += 1
                    logger.info("─── iteration %d ───", iteration)

                    payload = {**base_payload, "messages": messages}

                    # Stream cette itération
                    async for event in stream_openwebui_response(client, payload, headers):
                        etype = event[0]

                        if etype == "content":
                            yield f"data: {json.dumps({'content': event[1]})}\n\n"

                        elif etype == "reasoning":
                            yield f"data: {json.dumps({'reasoning': event[1]})}\n\n"

                        elif etype == "tool_status":
                            yield f"data: {json.dumps({'tool_status': event[1]})}\n\n"

                        elif etype == "error":
                            yield f"data: {json.dumps({'error': event[1]})}\n\n"
                            return

                        elif etype == "done":
                            pass

                    # Récupérer l'assistant message et le finish_reason
                    assistant_msg = stream_openwebui_response._last_assistant_msg
                    finish_reason = stream_openwebui_response._last_finish_reason

                    logger.info("  finish_reason: %s", finish_reason)
                    logger.info("  has tool_calls: %s", bool(assistant_msg.get("tool_calls")))

                    # Si pas de tool_calls, on a la réponse finale
                    if not assistant_msg.get("tool_calls") or finish_reason != "tool_calls":
                        logger.info("  → pas de tool_calls, réponse finale")
                        break

                    # ── Exécuter les tools ──────────────────────────────
                    tool_calls = assistant_msg["tool_calls"]
                    logger.info("  → %d tool_call(s) à exécuter", len(tool_calls))

                    # Ajouter l'assistant message (avec tool_calls) au messages
                    messages.append(assistant_msg)

                    # Exécuter chaque tool et ajouter les résultats
                    for tc in tool_calls:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except (json.JSONDecodeError, TypeError):
                            fn_args = {}

                        logger.info("  → executing: %s(%s)", fn_name, fn_args)

                        # Notifier le frontend qu'un tool s'exécute
                        yield f"data: {json.dumps({'tool_status': f'Exécution: {fn_name}({json.dumps(fn_args, ensure_ascii=False)})'})}\n\n"

                        try:
                            result = await execute_tool(fn_name, fn_args)
                            logger.info("  ← result: %s...", result[:200])
                        except Exception as e:
                            result = f"Erreur lors de l'exécution de {fn_name}: {e}"
                            logger.error("  ← error: %s", result)

                        # Ajouter le résultat au format OpenAI tool message
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": result,
                        })

                    # La boucle while va renvoyer à OpenWebUI avec les résultats
                    logger.info("  → re-requesting OpenWebUI with tool results")

                if iteration >= MAX_TOOL_ITERATIONS:
                    logger.warning("  → max iterations reached (%d)", MAX_TOOL_ITERATIONS)
                    yield f"data: {json.dumps({'error': 'Limite d itérations tool_call atteinte'})}\n\n"

        except httpx.ConnectError:
            logger.error("ConnectError to %s", OPENWEBUI_BASE_URL)
            yield f"data: {json.dumps({'error': f'Impossible de joindre OpenWebUI ({OPENWEBUI_BASE_URL}). Vérifiez OPENWEBUI_BASE_URL et que le service tourne.'})}\n\n"
        except Exception as e:
            logger.exception("Unexpected error in event_stream")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"
        logger.info("===== PROXY CHAT END =====")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
