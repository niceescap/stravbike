from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Activity as ActivityModel, Athlete
from api.routes.auth import get_current_coach

router = APIRouter()

@router.get("/{activity_id}")
def get_activity(activity_id: int, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    activity = db.query(ActivityModel).filter(
        ActivityModel.athlete_id == athlete.id,
        ActivityModel.strava_id == activity_id
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity
