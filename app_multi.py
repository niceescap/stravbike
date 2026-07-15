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

# Chemin pour trouver db/models.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db.models import (
    User, Athlete, Activity, PlannedSession,
    Competition, Comment, LLMAnalysis, AthleteSharing,
)

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
    """Force l'authentification. Lève HTTPException si pas de session."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
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
            "current_user_dict": _user_to_dict(user),
            "current_athlete_dict": _athlete_to_dict(athlete) if athlete else None,
        },
    )


@app.get("/activities/{activity_id}", response_class=HTMLResponse)
async def activity_detail_page(
    request: Request,
    activity_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Page détail d'une activité."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        raise HTTPException(status_code=404, detail="No athlete found")
    act = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.athlete_id == athlete.id)
        .first()
    )
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    return templates.TemplateResponse(
        request,
        "pages/activity_detail.html",
        {
            "service_key": SERVICE_KEY,
            "page": "activity_detail",
            "current_user_dict": _user_to_dict(user),
            "current_athlete_dict": _athlete_to_dict(athlete),
            "activity_id": activity_id,
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
            "current_user_dict": _user_to_dict(user),
            "current_athlete_dict": _athlete_to_dict(athlete) if athlete else None,
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
            "current_user_dict": _user_to_dict(user),
            "current_athlete_dict": _athlete_to_dict(athlete) if athlete else None,
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
# Routes — API (compatibilité avec le frontend JS existant)
# ────────────────────────────────────────────────────────────────────────────

@app.get("/api/athlete")
async def api_get_athlete(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Retourne le profil de l'athlète de l'utilisateur connecté."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        raise HTTPException(status_code=404, detail="No athlete linked to this user")
    return {
        "strava_id": athlete.strava_id,
        "firstname": athlete.firstname,
        "lastname": athlete.lastname,
        "ftp_watts": athlete.ftp_watts,
        "weight_kg": float(athlete.weight_kg) if athlete.weight_kg else None,
        "power_zones": athlete.power_zones,
        "heart_rate_zones": athlete.heart_rate_zones,
        "ytd_distance_km": float(athlete.ytd_distance_km) if athlete.ytd_distance_km else None,
        "ytd_elevation_m": athlete.ytd_elevation_m,
        "ytd_time_hours": float(athlete.ytd_time_hours) if athlete.ytd_time_hours else None,
        "city": athlete.city,
        "country": athlete.country,
    }


@app.get("/api/activities/")
async def api_get_activities(
    limit: int = 500,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Retourne les activités de l'athlète connecté."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        return []
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete.id)
        .order_by(Activity.start_date_local.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "strava_id": a.strava_id,
            "name": a.name,
            "sport_type": a.sport_type,
            "start_date": a.start_date.isoformat() if a.start_date else None,
            "start_date_local": a.start_date_local.isoformat() if a.start_date_local else None,
            "distance_km": float(a.distance_km) if a.distance_km else None,
            "moving_time_min": float(a.moving_time_min) if a.moving_time_min else None,
            "elevation_gain_m": float(a.elevation_gain_m) if a.elevation_gain_m else None,
            "avg_watts": float(a.avg_watts) if a.avg_watts else None,
            "weighted_avg_watts": float(a.weighted_avg_watts) if a.weighted_avg_watts else None,
            "avg_heartrate": float(a.avg_heartrate) if a.avg_heartrate else None,
            "avg_speed_kmh": float(a.avg_speed_kmh) if a.avg_speed_kmh else None,
            "intensity_factor": float(a.intensity_factor) if a.intensity_factor else None,
            "tss": float(a.tss) if a.tss else None,
            "athlete_id": athlete.strava_id,
        }
        for a in activities
    ]


@app.get("/api/activities/{activity_id}")
async def api_get_activity_detail(
    activity_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Retourne le détail d'une activité."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        raise HTTPException(status_code=404, detail="No athlete found")
    act = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.athlete_id == athlete.id)
        .first()
    )
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {
        "id": act.id,
        "strava_id": act.strava_id,
        "name": act.name,
        "sport_type": act.sport_type,
        "start_date": act.start_date.isoformat() if act.start_date else None,
        "start_date_local": act.start_date_local.isoformat() if act.start_date_local else None,
        "distance_km": float(act.distance_km) if act.distance_km else None,
        "moving_time_min": float(act.moving_time_min) if act.moving_time_min else None,
        "elevation_gain_m": float(act.elevation_gain_m) if act.elevation_gain_m else None,
        "avg_watts": float(act.avg_watts) if act.avg_watts else None,
        "weighted_avg_watts": float(act.weighted_avg_watts) if act.weighted_avg_watts else None,
        "max_watts": act.max_watts,
        "avg_heartrate": float(act.avg_heartrate) if act.avg_heartrate else None,
        "max_heartrate": act.max_heartrate,
        "avg_cadence": float(act.avg_cadence) if act.avg_cadence else None,
        "intensity_factor": float(act.intensity_factor) if act.intensity_factor else None,
        "tss": float(act.tss) if act.tss else None,
        "suffer_score": act.suffer_score,
        "kilojoules": float(act.kilojoules) if act.kilojoules else None,
        "streams_json": act.streams_json,
    }


@app.post("/api/activities/refresh")
async def api_refresh_activities(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Déclenche un import incrémental des activités Strava."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        raise HTTPException(status_code=404, detail="No athlete found")
    # TODO : appeler ingest_activities_multi en background
    return {"status": "queued", "athlete_id": athlete.strava_id}


@app.get("/api/calendar/week")
async def api_get_calendar_week(
    start_date: str,
    end_date: Optional[str] = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Retourne une liste PLATE d'événements calendrier (format attendu par calendar.js)."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        return []

    try:
        week_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")

    week_end = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        if end_date
        else week_start + timedelta(days=6)
    )

    # Activités
    activities = (
        db.query(Activity)
        .filter(
            Activity.athlete_id == athlete.id,
            Activity.start_date_local >= week_start,
            Activity.start_date_local <= week_end,
        )
        .all()
    )
    # Séances planifiées
    sessions = (
        db.query(PlannedSession)
        .filter(
            PlannedSession.athlete_id == athlete.id,
            PlannedSession.session_date >= week_start,
            PlannedSession.session_date <= week_end,
        )
        .all()
    )
    # Compétitions
    competitions = (
        db.query(Competition)
        .filter(
            Competition.athlete_id == athlete.id,
            Competition.competition_date >= week_start,
            Competition.competition_date <= week_end,
        )
        .all()
    )

    # Format PLAT attendu par calendar.js
    events = []

    # Activités → événements
    for a in activities:
        events.append({
            "activity_id": a.id,
            "session_id": None,
            "competition_id": None,
            "calendar_date": a.start_date_local.strftime("%Y-%m-%d") if a.start_date_local else None,
            "session_title": None,
            "session_description": None,
            "session_status": None,
            "session_validated": None,
            "session_ressenti": None,
            "activity_name": a.name,
            "moving_time_min": float(a.moving_time_min) if a.moving_time_min else None,
            "weighted_avg_watts": float(a.weighted_avg_watts) if a.weighted_avg_watts else None,
            "avg_heartrate": float(a.avg_heartrate) if a.avg_heartrate else None,
            "tss": float(a.tss) if a.tss else None,
            "intensity_factor": float(a.intensity_factor) if a.intensity_factor else None,
            "competition_name": None,
            "objective_level": None,
            "result_rank": None,
            "badge": "🚴",
        })

    # Séances → événements
    for s in sessions:
        # Badge logic
        matched_activity = next(
            (a for a in activities if a.start_date_local and a.start_date_local.date() == s.session_date and s.activity_id == a.id),
            None
        )
        if s.validated is True:
            badge = "✅"
        elif s.validated is False:
            badge = "❌"
        elif s.session_date < datetime.now().date() and not matched_activity:
            badge = "❌"
        elif matched_activity:
            badge = "🚴"
        else:
            badge = "⏳"

        events.append({
            "activity_id": None,
            "session_id": s.id,
            "competition_id": None,
            "calendar_date": s.session_date.strftime("%Y-%m-%d"),
            "session_title": s.title,
            "session_description": s.description,
            "session_status": s.status,
            "session_validated": s.validated,
            "session_ressenti": s.ressenti,
            "activity_name": None,
            "moving_time_min": None,
            "weighted_avg_watts": None,
            "avg_heartrate": None,
            "tss": None,
            "intensity_factor": None,
            "competition_name": None,
            "objective_level": None,
            "result_rank": None,
            "badge": badge,
        })

    # Compétitions → événements
    for c in competitions:
        badge = "🏆"
        events.append({
            "activity_id": None,
            "session_id": None,
            "competition_id": c.id,
            "calendar_date": c.competition_date.strftime("%Y-%m-%d"),
            "session_title": None,
            "session_description": None,
            "session_status": None,
            "session_validated": None,
            "session_ressenti": None,
            "activity_name": None,
            "moving_time_min": None,
            "weighted_avg_watts": None,
            "avg_heartrate": None,
            "tss": None,
            "intensity_factor": None,
            "competition_name": c.name,
            "objective_level": c.objective_level,
            "result_rank": c.result_rank,
            "badge": badge,
        })

    return events


@app.get("/api/comments/")
async def api_get_comments(
    activity_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Retourne les commentaires d'une activité."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        return []
    comments = (
        db.query(Comment)
        .filter(Comment.activity_id == activity_id, Comment.athlete_id == athlete.id)
        .order_by(Comment.created_at)
        .all()
    )
    return [
        {
            "id": c.id,
            "author_role": c.author_role,
            "comment": c.comment,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in comments
    ]


@app.post("/api/comments/")
async def api_add_comment(
    comment: str = Form(...),
    activity_id: int = Form(...),
    author_role: str = Form("athlete"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Ajoute un commentaire à une activité."""
    athlete = get_user_athlete(db, user)
    if not athlete:
        raise HTTPException(status_code=404, detail="No athlete found")
    act = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.athlete_id == athlete.id)
        .first()
    )
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    new_comment = Comment(
        athlete_id=athlete.id,
        user_id=user.id,
        activity_id=activity_id,
        comment=comment,
        author_role=author_role,
    )
    db.add(new_comment)
    db.commit()
    return {"status": "ok", "comment_id": new_comment.id}


@app.get("/api/activities/{activity_id}/streams")
async def api_get_activity_streams(
    activity_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Retourne les streams (courbes) d'une activité.
    Si non présents en DB, les fetch depuis Strava et les stocke.
    """
    from services.strava_client import get_strava_client

    athlete = get_user_athlete(db, user)
    if not athlete:
        raise HTTPException(status_code=404, detail="No athlete found")
    act = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.athlete_id == athlete.id)
        .first()
    )
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Déjà en DB ?
    if act.streams_json:
        return act.streams_json

    # Fetch depuis Strava
    STREAM_TYPES = ["time", "watts", "heartrate", "velocity_smooth", "cadence", "grade_smooth"]
    MAX_POINTS = 300

    def _downsample(values: list, target: int = MAX_POINTS) -> list:
        if not values or len(values) <= target:
            return values
        stride = len(values) / target
        return [values[int(i * stride)] for i in range(target)]

    try:
        strava_client = get_strava_client(db, athlete.id)
        strava_streams = strava_client.get_activity_streams(
            act.strava_id,
            types=STREAM_TYPES,
            resolution="medium",
        )
    except Exception as e:
        return {
            "error": str(e),
            "streams": {},
        }

    result = {}
    for st in STREAM_TYPES:
        stream = strava_streams.get(st)
        if stream and stream.data:
            result[st] = _downsample(list(stream.data))

    # Time axis in minutes
    if "time" in result and result["time"]:
        result["time_min"] = [round(t / 60.0, 2) for t in result["time"]]

    # Stocker en DB
    if result:
        act.streams_json = result
        db.commit()

    return result


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_multi:app", host="0.0.0.0", port=2024, reload=False)
