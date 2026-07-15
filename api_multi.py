# api_multi.py — Stravbike Multi-Athlete API
import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Chemin pour trouver db/models.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db.models import (
    User, Athlete, Activity, PlannedSession,
    Competition, Comment, LLMAnalysis, AthleteSharing,
)

# ────────────────────────────────────────────────────────────────────────────
# Configuration depuis .env
# ────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///db_multi_stravbike")
SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY")
if not SERVICE_KEY:
    raise RuntimeError("STRAVBIKE_SERVICE_KEY manquante dans .env")

# Connexion à la base
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

print(f"✅ Connexion à la base : {DATABASE_URL}")
app = FastAPI(title="Stravbike Multi-Athlete API")


# ────────────────────────────────────────────────────────────────────────────
# Dépendances DB et sécurité
# ────────────────────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def verify_service_key(x_api_key: str = Header(None)):
    if not SERVICE_KEY or x_api_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid service key")


# ────────────────────────────────────────────────────────────────────────────
# Routes — Athletes
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/athletes", dependencies=[Depends(verify_service_key)])
def list_athletes(db: Session = Depends(get_db)):
    athletes = db.query(Athlete).filter(Athlete.is_active == True).all()
    return [
        {
            "strava_id": a.strava_id,
            "name": f"{a.firstname} {a.lastname}".strip(),
            "ftp": a.ftp_watts,
            "weight": float(a.weight_kg) if a.weight_kg else None,
        }
        for a in athletes
    ]


@app.get("/api/athletes/search", dependencies=[Depends(verify_service_key)])
def search_athletes(name: str = Query(...), db: Session = Depends(get_db)):
    pattern = f"%{name}%"
    athletes = db.query(Athlete).filter(
        Athlete.is_active == True,
        (Athlete.firstname.ilike(pattern)) | (Athlete.lastname.ilike(pattern)),
    ).all()
    return [
        {
            "strava_id": a.strava_id,
            "name": f"{a.firstname} {a.lastname}".strip(),
            "ftp": a.ftp_watts,
            "weight": float(a.weight_kg) if a.weight_kg else None,
        }
        for a in athletes
    ]


@app.get("/api/athletes/{athlete_strava_id}/profile", dependencies=[Depends(verify_service_key)])
def get_athlete_profile(athlete_strava_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(
        Athlete.strava_id == athlete_strava_id,
        Athlete.is_active == True,
    ).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return {
        "name": f"{athlete.firstname} {athlete.lastname}".strip(),
        "ftp": athlete.ftp_watts,
        "weight": float(athlete.weight_kg) if athlete.weight_kg else None,
        "power_zones": athlete.power_zones,
        "heart_rate_zones": athlete.heart_rate_zones,
        "ytd_distance_km": float(athlete.ytd_distance_km) if athlete.ytd_distance_km else None,
        "ytd_elevation_m": athlete.ytd_elevation_m,
        "ytd_time_hours": float(athlete.ytd_time_hours) if athlete.ytd_time_hours else None,
        "city": athlete.city,
        "country": athlete.country,
    }


# ────────────────────────────────────────────────────────────────────────────
# Routes — Calendar
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/athletes/{athlete_strava_id}/calendar/week", dependencies=[Depends(verify_service_key)])
def week_calendar(
    athlete_strava_id: int,
    start_date: str = Query(..., description="YYYY-MM-DD (lundi)"),
    db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    try:
        week_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")
    week_end = week_start + timedelta(days=6)

    activities = db.query(Activity).filter(
        Activity.athlete_id == athlete.id,
        Activity.start_date_local >= week_start,
        Activity.start_date_local <= week_end,
    ).order_by(Activity.start_date_local).all()

    sessions = db.query(PlannedSession).filter(
        PlannedSession.athlete_id == athlete.id,
        PlannedSession.session_date >= week_start,
        PlannedSession.session_date <= week_end,
    ).order_by(PlannedSession.session_date).all()

    competitions = db.query(Competition).filter(
        Competition.athlete_id == athlete.id,
        Competition.competition_date >= week_start,
        Competition.competition_date <= week_end,
    ).all()

    return {
        "start_date": start_date,
        "end_date": week_end.strftime("%Y-%m-%d"),
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "date": a.start_date_local.strftime("%Y-%m-%d"),
                "distance_km": float(a.distance_km) if a.distance_km else None,
                "moving_time_min": float(a.moving_time_min) if a.moving_time_min else None,
                "elevation_gain_m": float(a.elevation_gain_m) if a.elevation_gain_m else None,
                "avg_watts": float(a.avg_watts) if a.avg_watts else None,
                "tss": float(a.tss) if a.tss else None,
            }
            for a in activities
        ],
        "planned_sessions": [
            {
                "id": s.id,
                "date": s.session_date.strftime("%Y-%m-%d"),
                "title": s.title,
                "description": s.description,
                "target_tss": float(s.target_tss) if s.target_tss else None,
                "status": s.status,
                "validated": s.validated,
            }
            for s in sessions
        ],
        "competitions": [
            {
                "id": c.id,
                "name": c.name,
                "date": c.competition_date.strftime("%Y-%m-%d"),
                "objective_level": c.objective_level,
                "distance_km": float(c.distance_km) if c.distance_km else None,
            }
            for c in competitions
        ],
    }


# ────────────────────────────────────────────────────────────────────────────
# Routes — Activités (daily / monthly / yearly)
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/athletes/{athlete_strava_id}/activities/daily", dependencies=[Depends(verify_service_key)])
def daily_activities(
    athlete_strava_id: int,
    date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    activities = db.query(Activity).filter(
        Activity.athlete_id == athlete.id,
        Activity.start_date_local >= day,
        Activity.start_date_local < day + timedelta(days=1),
    ).order_by(Activity.start_date_local).all()
    return {
        "date": date,
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "start_date": a.start_date_local.strftime("%Y-%m-%d %H:%M:%S"),
                "distance_km": float(a.distance_km) if a.distance_km else None,
                "moving_time_min": float(a.moving_time_min) if a.moving_time_min else None,
                "elevation_gain_m": float(a.elevation_gain_m) if a.elevation_gain_m else None,
                "avg_watts": float(a.avg_watts) if a.avg_watts else None,
                "tss": float(a.tss) if a.tss else None,
            }
            for a in activities
        ],
    }


@app.get("/api/athletes/{athlete_strava_id}/activities/monthly", dependencies=[Depends(verify_service_key)])
def monthly_activities(
    athlete_strava_id: int,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    start = date(year, month, 1)
    end = date(year + 1, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
    activities = db.query(Activity).filter(
        Activity.athlete_id == athlete.id,
        Activity.start_date_local >= start,
        Activity.start_date_local < end,
    ).order_by(Activity.start_date_local).all()
    return {
        "year": year,
        "month": month,
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "date": a.start_date_local.strftime("%Y-%m-%d"),
                "distance_km": float(a.distance_km) if a.distance_km else None,
                "moving_time_min": float(a.moving_time_min) if a.moving_time_min else None,
                "elevation_gain_m": float(a.elevation_gain_m) if a.elevation_gain_m else None,
                "avg_watts": float(a.avg_watts) if a.avg_watts else None,
                "tss": float(a.tss) if a.tss else None,
            }
            for a in activities
        ],
    }


@app.get("/api/athletes/{athlete_strava_id}/activities/yearly", dependencies=[Depends(verify_service_key)])
def yearly_activities(
    athlete_strava_id: int,
    year: int = Query(...),
    db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    activities = db.query(Activity).filter(
        Activity.athlete_id == athlete.id,
        Activity.start_date_local >= start,
        Activity.start_date_local < end,
    ).order_by(Activity.start_date_local).all()
    return {
        "year": year,
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "date": a.start_date_local.strftime("%Y-%m-%d"),
                "distance_km": float(a.distance_km) if a.distance_km else None,
                "moving_time_min": float(a.moving_time_min) if a.moving_time_min else None,
                "elevation_gain_m": float(a.elevation_gain_m) if a.elevation_gain_m else None,
                "avg_watts": float(a.avg_watts) if a.avg_watts else None,
                "tss": float(a.tss) if a.tss else None,
            }
            for a in activities
        ],
    }


# ────────────────────────────────────────────────────────────────────────────
# Routes — Compétitions
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/athletes/{athlete_strava_id}/competitions", dependencies=[Depends(verify_service_key)])
def get_competitions(athlete_strava_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    comps = db.query(Competition).filter(Competition.athlete_id == athlete.id).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "date": c.competition_date.strftime("%Y-%m-%d"),
            "location": c.location,
            "distance_km": float(c.distance_km) if c.distance_km else None,
            "objective_level": c.objective_level,
            "result_time": str(c.result_time) if c.result_time else None,
            "result_rank": c.result_rank,
        }
        for c in comps
    ]


# ────────────────────────────────────────────────────────────────────────────
# Routes — Séances planifiées
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/athletes/{athlete_strava_id}/sessions", dependencies=[Depends(verify_service_key)])
def get_planned_sessions(
    athlete_strava_id: int,
    week: str = Query(..., description="YYYY-MM-DD (lundi)"),
    db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    try:
        week_start = datetime.strptime(week, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="week must be YYYY-MM-DD")
    week_end = week_start + timedelta(days=6)
    sessions = db.query(PlannedSession).filter(
        PlannedSession.athlete_id == athlete.id,
        PlannedSession.session_date >= week_start,
        PlannedSession.session_date <= week_end,
    ).order_by(PlannedSession.session_date).all()
    return [
        {
            "id": s.id,
            "date": s.session_date.strftime("%Y-%m-%d"),
            "title": s.title,
            "description": s.description,
            "sport_type": s.sport_type,
            "target_duration_min": s.target_duration_min,
            "target_tss": float(s.target_tss) if s.target_tss else None,
            "status": s.status,
            "validated": s.validated,
            "ressenti": s.ressenti,
            "athlete_comment": s.athlete_comment,
        }
        for s in sessions
    ]


# ────────────────────────────────────────────────────────────────────────────
# Routes — Activités (détail)
# ────────────────────────────────────────────────────────────────────────────
@app.get("/api/activities/{activity_id}", dependencies=[Depends(verify_service_key)])
def get_activity_detail(
    activity_id: int,
    athlete_id: Optional[int] = Query(None, description="Strava ID for verification"),
    db: Session = Depends(get_db),
):
    act = db.query(Activity).filter(Activity.id == activity_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    if athlete_id:
        athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_id).first()
        if not athlete or act.athlete_id != athlete.id:
            raise HTTPException(status_code=403, detail="Activity does not belong to this athlete")
    return {
        "id": act.id,
        "name": act.name,
        "sport_type": act.sport_type,
        "start_date": act.start_date.strftime("%Y-%m-%d %H:%M:%S") if act.start_date else None,
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
    }


# ────────────────────────────────────────────────────────────────────────────
# Routes — Refresh activités
# ────────────────────────────────────────────────────────────────────────────
@app.post("/api/athletes/{athlete_strava_id}/activities/refresh", dependencies=[Depends(verify_service_key)])
def refresh_activities(athlete_strava_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_strava_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    # TODO : intégrer l'appel à ingest_activities.py avec get_strava_client(db, athlete.id)
    return {"status": "queued", "athlete": f"{athlete.firstname} {athlete.lastname}"}


# ────────────────────────────────────────────────────────────────────────────
# Routes — Commentaires
# ────────────────────────────────────────────────────────────────────────────
@app.post("/api/comments", dependencies=[Depends(verify_service_key)])
def add_comment(
    activity_id: int = Query(...),
    comment: str = Query(...),
    athlete_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(1),
    db: Session = Depends(get_db),
):
    act = db.query(Activity).filter(Activity.id == activity_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    if athlete_id:
        athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_id).first()
        if not athlete or act.athlete_id != athlete.id:
            raise HTTPException(status_code=403, detail="Activity does not belong to this athlete")
    new_comment = Comment(
        athlete_id=act.athlete_id,
        user_id=user_id,
        activity_id=activity_id,
        comment=comment,
    )
    db.add(new_comment)
    db.commit()
    return {"status": "ok", "comment_id": new_comment.id}
