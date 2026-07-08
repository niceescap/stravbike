"""
Proxy chat → OpenWebUI.
Le modèle personnalisé (avec tool stravbike_tool.py rattaché) vit côté OpenWebUI.
Ce routeur forward les messages du frontend vers l'API OpenWebUI et stream la réponse.

⚠️ DIAGNOSTIC TEMPORAIRE : stream désactivé pour inspecter la réponse JSON brute.
    À restaurer après analyse des champs tool_calls / finish_reason / message / content.
"""
import os
import json
import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from api.dependencies import verify_service_key

load_dotenv()

router = APIRouter()

OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "")


class ChatMessage(BaseModel):
    message: str


@router.post("/")
async def chat_endpoint(msg: ChatMessage):
    """Proxy non-streaming vers OpenWebUI — DIAGNOSTIC : inspecte la réponse JSON brute."""

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
        "stream": False,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{OPENWEBUI_BASE_URL}/api/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

    # ── DIAGNOSTIC : afficher la réponse JSON brute ──────────────────
    print("===== RAW OPENWEBUI RESPONSE =====")
    print(json.dumps(resp.json(), indent=2))
    print("===== END RAW RESPONSE =====")

    # On retourne la réponse brute telle quelle — pas de parsing, pas de logique métier.
    return resp.json()
