"""
api/routes/web.py — Router frontend (pages HTML + proxy chat OpenWebUI)

Sert les pages Jinja2 et proxy les messages du chat vers l'API OpenWebUI.
Les routes web ne sont PAS derrière verify_service_key (elles servent du HTML).
La service key est injectée dans les templates via Jinja2 pour que le JS
frontend puisse l'envoyer dans X-API-Key à chaque appel API.

Le proxy /chat/send forward les messages vers OpenWebUI (API OpenAI-compatible).
Le modèle OpenWebUI a l'outil stravbike_tool.py rattaché → le LLM accède à la DB.
"""

import os
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import httpx

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY", "")
OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "http://localhost:8080")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "")

# ── Pages HTML ──────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse(url="/calendar")

@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request):
    return templates.TemplateResponse("pages/calendar.html", {
        "request": request, "service_key": SERVICE_KEY, "active_page": "calendar"
    })

@router.get("/activities", response_class=HTMLResponse)
def activities_page(request: Request):
    return templates.TemplateResponse("pages/activities.html", {
        "request": request, "service_key": SERVICE_KEY, "active_page": "activities"
    })

@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse("pages/chat.html", {
        "request": request, "service_key": SERVICE_KEY, "active_page": "chat"
    })

@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    return templates.TemplateResponse("pages/profile.html", {
        "request": request, "service_key": SERVICE_KEY, "active_page": "profile"
    })

# ── Proxy chat → OpenWebUI (streaming SSE) ──────────────

@router.post("/chat/send")
async def chat_send(request: Request):
    """
    Proxy les messages du frontend vers l'API OpenWebUI.
    Le modèle OpenWebUI a l'outil stravbike_tool.py rattaché.
    Streaming SSE → le frontend lit les chunks en temps réel.
    """
    body = await request.json()
    messages = body.get("messages", [])

    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENWEBUI_MODEL,
        "messages": messages,
        "stream": True
    }

    async def stream():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{OPENWEBUI_BASE_URL}/api/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        yield f"{line}\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
