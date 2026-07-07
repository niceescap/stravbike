from fastapi import APIRouter, Depends

router = APIRouter()

@router.post("/analyze")
def analyze(payload: dict):
    return {"message": "LLM analysis not implemented yet"}
