from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from db.database import get_db
from api.routes.auth import get_current_coach
from datetime import date, timedelta

router = APIRouter()

@router.get("/week")
def calendar_week(start_date: date = Query(...), db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    # On exploite la vue calendar_view pour la semaine
    end_date = start_date + timedelta(days=7)
    query = text("""
        SELECT * FROM calendar_view
        WHERE calendar_date >= :start AND calendar_date < :end
        ORDER BY calendar_date
    """)
    result = db.execute(query, {"start": start_date, "end": end_date})
    rows = result.mappings().all()
    return [dict(row) for row in rows]
