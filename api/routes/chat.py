"""
Proxy chat → OpenWebUI.
Le modèle personnalisé (avec tool stravbike_tool.py rattaché) vit côté OpenWebUI.
Ce routeur forward les messages du frontend vers l'API OpenWebUI et stream la réponse.
"""
import os
import json
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from api.dependencies import verify_service_key

router = APIRouter()

OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "")


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

    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENWEBUI_MODEL,
        "messages": [{"role": "user", "content": msg.message}],
        "stream": True,
    }

    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{OPENWEBUI_BASE_URL}/api/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            chunk = json.loads(data)
                            content = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': f'Impossible de joindre OpenWebUI ({OPENWEBUI_BASE_URL}). Vérifiez OPENWEBUI_BASE_URL et que le service tourne.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
