from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import Athlete, CoachComment
from api.models import CommentCreate, CommentOut
from api.routes.auth import get_current_coach

router = APIRouter()

@router.post("/", response_model=CommentOut)
def create_comment(comment: CommentCreate, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    db_comment = CoachComment(athlete_id=athlete.id, **comment.dict())
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

@router.get("/", response_model=list[CommentOut])
def list_comments(activity_id: int = None, session_id: int = None, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    query = db.query(CoachComment).filter(CoachComment.athlete_id == athlete.id)
    if activity_id:
        query = query.filter(CoachComment.activity_id == activity_id)
    if session_id:
        query = query.filter(CoachComment.session_id == session_id)
    return query.all()

@router.delete("/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db), coach=Depends(get_current_coach)):
    athlete = db.query(Athlete).first()
    comment = db.query(CoachComment).filter(CoachComment.id == comment_id, CoachComment.athlete_id == athlete.id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(comment)
    db.commit()
    return {"ok": True}
