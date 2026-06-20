from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Athlete, Competition
from api.models import CompetitionCreate, CompetitionOut
from api.routes.auth import get_current_coach

router = APIRouter()

@router.post("/", response_model=CompetitionOut)
def create_competition(comp: CompetitionCreate, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    db_comp = Competition(athlete_id=athlete.id, **comp.dict())
    db.add(db_comp)
    db.commit()
    db.refresh(db_comp)
    return db_comp

@router.get("/", response_model=list[CompetitionOut])
def list_competitions(db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        return []
    return db.query(Competition).filter(Competition.athlete_id == athlete.id).all()

@router.get("/{comp_id}", response_model=CompetitionOut)
def get_competition(comp_id: int, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    comp = db.query(Competition).filter(Competition.id == comp_id, Competition.athlete_id == athlete.id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    return comp

@router.delete("/{comp_id}")
def delete_competition(comp_id: int, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    comp = db.query(Competition).filter(Competition.id == comp_id, Competition.athlete_id == athlete.id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    db.delete(comp)
    db.commit()
    return {"ok": True}
