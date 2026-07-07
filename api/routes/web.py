"""
Routes web — servent les pages HTML via Jinja2.
L'auth (X-API-Key) est injectée côté serveur dans les templates.
Aucune dépendance sur verify_service_key ici : les pages HTML ne sont pas des API.
"""
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY", "")


def _ctx(request: Request, **kwargs):
    """Contexte de template commun."""
    ctx = {"request": request, "service_key": SERVICE_KEY}
    ctx.update(kwargs)
    return ctx


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse(url="/calendar", status_code=302)


@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request):
    return templates.TemplateResponse("pages/calendar.html", _ctx(request, page="calendar"))


@router.get("/activities", response_class=HTMLResponse)
def activities_page(request: Request):
    return templates.TemplateResponse("pages/activities.html", _ctx(request, page="activities"))


@router.get("/activities/{activity_id}", response_class=HTMLResponse)
def activity_detail_page(request: Request, activity_id: int):
    return templates.TemplateResponse(
        "pages/activity_detail.html",
        _ctx(request, page="activities", activity_id=activity_id),
    )


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse("pages/chat.html", _ctx(request, page="chat"))


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    return templates.TemplateResponse("pages/profile.html", _ctx(request, page="profile"))
