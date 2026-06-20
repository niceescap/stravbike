from fastapi import APIRouter, Depends
from api.routes.auth import get_current_coach

router = APIRouter()

@router.post("/analyze")
def analyze(payload: dict, coach=Depends(get_current_coach)):
    return {"message": "LLM analysis not implemented yet"}
