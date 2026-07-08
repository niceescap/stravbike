from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from db.database import get_db
from datetime import date, timedelta

router = APIRouter()

@router.get("/week")
def calendar_week(
    start_date: date = Query(...),
    end_date: date = Query(None),
    db: Session = Depends(get_db),
):
    """
    Retourne les entrées du calendrier entre start_date et end_date.
    Si end_date n'est pas fourni, retourne 7 jours depuis start_date (backward compat).
    FullCalendar en month view envoie ~42 jours de plage visible.
    """
    end = end_date if end_date else start_date + timedelta(days=7)
    # calendar_view ne filtre pas sur athlete_id (mono-athlète) — pas d'impact des orphelins
    query = text("""
        SELECT * FROM calendar_view
        WHERE calendar_date >= :start AND calendar_date < :end
        ORDER BY calendar_date
    """)
    result = db.execute(query, {"start": start_date, "end": end})
    rows = result.mappings().all()
    return [dict(row) for row in rows]
