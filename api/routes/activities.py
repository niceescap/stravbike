from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Activity as ActivityModel
from ingestion.ingest_activities import incremental_refresh, fetch_and_store_streams

router = APIRouter()


@router.get("/")
def list_activities(limit: int = Query(500, ge=1, le=1000), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """Liste toutes les activités, triées par date décroissante.
    Mono-athlète : pas de filtre sur athlete_id (activités orphelines historiques)."""
    activities = (
        db.query(ActivityModel)
        .order_by(ActivityModel.start_date_local.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return activities


@router.get("/{activity_id}")
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    """Détail d'une activité par son ID interne.
    Mono-athlète : pas de filtre sur athlete_id."""
    activity = db.query(ActivityModel).filter(
        ActivityModel.id == activity_id
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.post("/refresh")
def refresh_activities(db: Session = Depends(get_db)):
    """Déclenche une synchronisation incrémentale depuis Strava (nouvelles activités)."""
    from db.models import Athlete
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    try:
        incremental_refresh(db, athlete.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync error: {e}")
    return {"ok": True, "message": "Synchronisation incrémentale déclenchée."}
