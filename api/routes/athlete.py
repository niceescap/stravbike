from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Athlete
from api.routes.auth import get_current_coach

router = APIRouter()

@router.get("")
def get_athlete(db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        return {"message": "No athlete found"}
    return {
        "id": athlete.id,
        "strava_id": athlete.strava_id,
        "firstname": athlete.firstname,
        "lastname": athlete.lastname,
        "ftp_watts": athlete.ftp_watts,
        "weight_kg": float(athlete.weight_kg) if athlete.weight_kg else None,
        "power_zones": athlete.power_zones,
        "heart_rate_zones": athlete.heart_rate_zones,
        "ytd_distance_km": float(athlete.ytd_distance_km) if athlete.ytd_distance_km else None,
        "ytd_elevation_m": athlete.ytd_elevation_m,
        "ytd_time_hours": float(athlete.ytd_time_hours) if athlete.ytd_time_hours else None
    }
