from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List, Any

# ---------- Auth ----------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ---------- Athlete ----------
class AthleteOut(BaseModel):
    id: int
    strava_id: int
    firstname: Optional[str]
    lastname: Optional[str]
    ftp_watts: Optional[int]
    weight_kg: Optional[float]
    power_zones: Optional[Any] = None
    heart_rate_zones: Optional[Any] = None
    ytd_distance_km: Optional[float]
    ytd_elevation_m: Optional[int]
    ytd_time_hours: Optional[float]

    class Config:
        orm_mode = True

# ---------- Activity ----------
class ActivityOut(BaseModel):
    id: int
    strava_id: int
    name: Optional[str]
    sport_type: Optional[str]
    start_date: Optional[datetime]
    start_date_local: Optional[datetime]
    distance_km: Optional[float]
    moving_time_min: Optional[float]
    avg_watts: Optional[float]
    weighted_avg_watts: Optional[float]
    avg_heartrate: Optional[float]
    intensity_factor: Optional[float]
    tss: Optional[float]
    streams_json: Optional[Any] = None

    class Config:
        orm_mode = True

# ---------- Session ----------
class SessionCreate(BaseModel):
    session_date: date
    title: str
    description: Optional[str] = None
    sport_type: Optional[str] = "Ride"
    target_duration_min: Optional[int] = None
    target_tss: Optional[float] = None
    target_if_min: Optional[float] = None
    target_if_max: Optional[float] = None
    target_distance_km: Optional[float] = None

class SessionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    validated: Optional[bool] = None
    ressenti: Optional[int] = None
    fatigue: Optional[int] = None
    athlete_comment: Optional[str] = None

class SessionOut(SessionCreate):
    id: int
    status: str
    activity_id: Optional[int]
    validated: Optional[bool]
    validation_score: Optional[float]
    ressenti: Optional[int]
    fatigue: Optional[int]
    athlete_comment: Optional[str]
    created_by: str
    created_at: datetime

    class Config:
        orm_mode = True

# ---------- Competition ----------
class CompetitionCreate(BaseModel):
    competition_date: date
    name: str
    location: Optional[str] = None
    sport_type: Optional[str] = "Ride"
    distance_km: Optional[float] = None
    objective_level: Optional[str] = "B"
    preparation_notes: Optional[str] = None

class CompetitionUpdate(BaseModel):
    result_time: Optional[str] = None
    result_rank: Optional[int] = None
    result_participants: Optional[int] = None
    ressenti: Optional[int] = None
    result_notes: Optional[str] = None

class CompetitionOut(CompetitionCreate):
    id: int
    result_time: Optional[str]
    result_rank: Optional[int]
    ressenti: Optional[int]
    result_notes: Optional[str]
    llm_analysis_id: Optional[int]

    class Config:
        orm_mode = True

# ---------- Comment ----------
class CommentCreate(BaseModel):
    activity_id: int
    session_id: Optional[int] = None
    comment: str
    author_role: str = "coach"

class CommentOut(CommentCreate):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

# ---------- LLM ----------
class LLMAnalysisRequest(BaseModel):
    analysis_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    payload: dict = {}
