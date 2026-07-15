"""
app_multi.py — Stravbike Multi-User Frontend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
App FastAPI qui sert l'interface multi-utilisateur :
  - Login par email (pas de mot de passe, beta)
  - Calendrier dynamique (auto-refresh à l'ouverture)
  - Chat IA (utilise le modèle LLM alloué à l'utilisateur)
  - Profil (tier, modèle, bouton PayPal)

Démarrage :
    uvicorn app_multi:app --host 0.0.0.0 --port 2025
"""

import os
import sys
import secrets
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

# ────────────────────────────────────────────────────────────────────────────
# Setup
# ────────────────────────────────────────────────────────────────────────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from db.database import SessionLocal, init_db
from db.models import User, Athlete

app = FastAPI(title="Stravbike Multi-User")

# Montage des statics
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory="frontend/templates")

# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///db_multi_stravbike")
SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
PAYPAL_URL = os.getenv("PAYPAL_URL", "https://paypal.me/NiceeCap")

# Cookie config
COOKIE_NAME = "stravbike_session"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 jours


# ────────────────────────────────────────────────────────────────────────────
# Helpers session (cookie signé HMAC)
# ────────────────────────────────────────────────────────────────────────────

def _sign_session(user_id: int) -> str:
    """Signe un user_id avec HMAC-SHA256."""
    payload = f"{user_id}"
    signature = secrets.compare_digest(
        payload,  # dummy — on utilise hmac directement
        payload,
    )
    import hmac
    sig = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{sig}"


def _verify_session(cookie_value: str) -> Optional[int]:
    """Vérifie et décode un cookie de session. Retourne user_id ou None."""
    import hmac
    try:
        user_id_str, sig = cookie_value.rsplit(":", 1)
        expected = hmac.new(
            SESSION_SECRET.encode(),
            user_id_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return None
        return int(user_id_str)
    except (ValueError, Exception):
        return None


# ────────────────────────────────────────────────────────────────────────────
# Dépendances
# ────────────────────────────────────────────────────────────────────────────

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Récupère l'utilisateur depuis le cookie de session."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    user_id = _verify_session(cookie)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Force l'authentification. Redirige vers /login si pas de session."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user


def get_user_athlete(db: Session, user: User) -> Optional[Athlete]:
    """Récupère le premier athlète actif de l'utilisateur."""
    return (
        db.query(Athlete)
        .filter(Athlete.owner_user_id == user.id, Athlete.is_active == True)
        .first()
    )


# ────────────────────────────────────────────────────────────────────────────
# Startup
# ────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    init_db()
    print(f"✅ Stravbike Multi-User démarré (port 2025)")


# ────────────────────────────────────────────────────────────────────────────
# Helpers de sérialisation (objets SQLAlchemy → dicts JSON-safe)
# ────────────────────────────────────────────────────────────────────────────

def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "tier": user.tier,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _athlete_to_dict(athlete: Athlete) -> dict:
    return {
        "id": athlete.id,
        "strava_id": athlete.strava_id,
        "firstname": athlete.firstname,
        "lastname": athlete.lastname,
        "ftp_watts": athlete.ftp_watts,
        "weight_kg": float(athlete.weight_kg) if athlete.weight_kg else None,
    }


# ────────────────────────────────────────────────────────────────────────────
# Routes — Auth
# ────────────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    """Page de login — formulaire email."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": error,
            "service_key": SERVICE_KEY,
        },
    )


@app.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    """Traite la soumission du formulaire de login."""
    user = db.query(User).filter(User.email.ilike(email.strip())).first()
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Aucun compte trouvé avec cet email.",
                "service_key": SERVICE_KEY,
            },
            status_code=400,
        )

    # Mettre à jour last_login_at
    user.last_login_at = datetime.now()
    db.commit()

    # Créer le cookie de session
    session_cookie = _sign_session(user.id)
    response = RedirectResponse(url="/calendar", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        session_cookie,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    """Déconnexion — supprime le cookie."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ────────────────────────────────────────────────────────────────────────────
# Routes — Pages (nécessite authentification)
# ────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Page d'accueil — redirige selon l'état de session."""
    if user:
        return RedirectResponse(url="/calendar", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Page calendrier — clone de la version mono, avec contexte utilisateur."""
    athlete = get_user_athlete(db, user)
    return templates.TemplateResponse(
        request,
        "pages/calendar.html",
        {
            "service_key": SERVICE_KEY,
            "page": "calendar",
            "current_user_dict": _user_to_dict(user),
            "current_athlete_dict": _athlete_to_dict(athlete) if athlete else None,
        },
    )


@app.get("/activities", response_class=HTMLResponse)
async def activities_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Page liste des activités."""
    athlete = get_user_athlete(db, user)
    return templates.TemplateResponse(
        request,
        "pages/activities.html",
        {
            "service_key": SERVICE_KEY,
            "page": "activities",
            "current_user": user,
            "current_athlete": athlete,
        },
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Page chat — utilise le modèle LLM alloué à l'utilisateur."""
    from services.llm_router import get_model_for_user, get_tier_for_user

    athlete = get_user_athlete(db, user)
    model = get_model_for_user(db, user.id)
    tier_info = get_tier_for_user(db, user.id)

    return templates.TemplateResponse(
        request,
        "pages/chat.html",
        {
            "service_key": SERVICE_KEY,
            "page": "chat",
            "current_user": user,
            "current_athlete": athlete,
            "llm_model": model,
            "llm_tier": tier_info["label"],
        },
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Page profil — tier, modèle, bouton PayPal."""
    from services.llm_router import get_tier_for_user

    athlete = get_user_athlete(db, user)
    tier_info = get_tier_for_user(db, user.id)

    return templates.TemplateResponse(
        request,
        "pages/profile.html",
        {
            "service_key": SERVICE_KEY,
            "page": "profile",
            "current_user": user,
            "current_athlete": athlete,
            "tier_info": tier_info,
            "paypal_url": PAYPAL_URL,
        },
    )


# ────────────────────────────────────────────────────────────────────────────
# Routes — API interne (pour le frontend multi-user)
# ────────────────────────────────────────────────────────────────────────────

@app.get("/api/me")
async def get_current_user_api(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Retourne les infos de l'utilisateur courant."""
    from services.llm_router import get_tier_for_user

    athlete = get_user_athlete(db, user)
    tier_info = get_tier_for_user(db, user.id)

    return {
        "id": user.id,
        "email": user.email,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "tier": tier_info["tier"],
        "tier_label": tier_info["label"],
        "llm_model": tier_info["current_model"],
        "athlete": {
            "id": athlete.id if athlete else None,
            "strava_id": athlete.strava_id if athlete else None,
            "name": f"{athlete.firstname} {athlete.lastname}".strip() if athlete else None,
            "ftp": athlete.ftp_watts if athlete else None,
        } if athlete else None,
    }


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_multi:app", host="0.0.0.0", port=2024, reload=False)
