from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Athlete, PlannedSession
from api.models import SessionCreate, SessionUpdate, SessionOut
from api.routes.auth import get_current_coach

router = APIRouter()

@router.post("/", response_model=SessionOut)
def create_session(session: SessionCreate, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    db_session = PlannedSession(athlete_id=athlete.id, **session.dict())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

@router.get("/", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        return []
    return db.query(PlannedSession).filter(PlannedSession.athlete_id == athlete.id).all()

@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    session = db.query(PlannedSession).filter(PlannedSession.id == session_id, PlannedSession.athlete_id == athlete.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@router.put("/{session_id}", response_model=SessionOut)
def update_session(session_id: int, session_update: SessionUpdate, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    session = db.query(PlannedSession).filter(PlannedSession.id == session_id, PlannedSession.athlete_id == athlete.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    for key, value in session_update.dict(exclude_unset=True).items():
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return session

@router.delete("/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    session = db.query(PlannedSession).filter(PlannedSession.id == session_id, PlannedSession.athlete_id == athlete.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"ok": True}
