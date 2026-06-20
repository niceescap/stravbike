from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, Text, DateTime, Date, ForeignKey, JSON, Interval, CHAR, Numeric
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Athlete(Base):
    __tablename__ = "athlete"

    id = Column(Integer, primary_key=True, index=True)
    strava_id = Column(BigInteger, unique=True, nullable=False)
    firstname = Column(String(100))
    lastname = Column(String(100))
    city = Column(String(100))
    country = Column(String(100))
    profile_pic_url = Column(Text)
    ftp_watts = Column(Integer, default=237)
    weight_kg = Column(Numeric(5, 2), default=71.0)
    power_zones = Column(JSON)
    heart_rate_zones = Column(JSON)
    ytd_distance_km = Column(Numeric(8, 2))
    ytd_elevation_m = Column(Integer)
    ytd_time_hours = Column(Numeric(6, 2))
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    activities = relationship("Activity", back_populates="athlete", cascade="all, delete-orphan")
    planned_sessions = relationship("PlannedSession", back_populates="athlete", cascade="all, delete-orphan")
    competitions = relationship("Competition", back_populates="athlete", cascade="all, delete-orphan")
    coach_comments = relationship("CoachComment", back_populates="athlete", cascade="all, delete-orphan")

class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    strava_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String(255))
    sport_type = Column(String(50))
    start_date = Column(DateTime(timezone=True))
    start_date_local = Column(DateTime(timezone=True))
    distance_m = Column(Numeric(10, 2))
    moving_time_s = Column(Integer)
    elapsed_time_s = Column(Integer)
    elevation_gain_m = Column(Numeric(8, 2))
    avg_watts = Column(Numeric(8, 2))
    weighted_avg_watts = Column(Numeric(8, 2))
    max_watts = Column(Integer)
    avg_heartrate = Column(Numeric(5, 2))
    max_heartrate = Column(Integer)
    avg_cadence = Column(Numeric(5, 2))
    kilojoules = Column(Numeric(8, 2))
    suffer_score = Column(Integer)
    distance_km = Column(Numeric(8, 3))
    moving_time_min = Column(Numeric(8, 2))
    avg_speed_kmh = Column(Numeric(6, 2))
    intensity_factor = Column(Numeric(5, 3))
    tss = Column(Numeric(8, 2))
    streams_json = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    athlete_id = Column(Integer, ForeignKey("athlete.id", ondelete="CASCADE"))
    athlete = relationship("Athlete", back_populates="activities")
    comments = relationship("CoachComment", back_populates="activity", cascade="all, delete-orphan")
    sessions = relationship("PlannedSession", back_populates="activity")

class PlannedSession(Base):
    __tablename__ = "planned_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_date = Column(Date, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    sport_type = Column(String(50), default="Ride")
    target_duration_min = Column(Integer)
    target_tss = Column(Numeric(6, 2))
    target_if_min = Column(Numeric(4, 3))
    target_if_max = Column(Numeric(4, 3))
    target_distance_km = Column(Numeric(7, 2))
    status = Column(String(20), default="planned")
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True)
    validated = Column(Boolean)
    validation_score = Column(Numeric(5, 2))
    validation_detail = Column(JSON)
    ressenti = Column(Integer)
    fatigue = Column(Integer)
    athlete_comment = Column(Text)
    created_by = Column(String(50), default="coach")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    athlete_id = Column(Integer, ForeignKey("athlete.id", ondelete="CASCADE"))
    athlete = relationship("Athlete", back_populates="planned_sessions")
    activity = relationship("Activity", back_populates="sessions")
    comments = relationship("CoachComment", back_populates="session", cascade="all, delete-orphan")

class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True, index=True)
    competition_date = Column(Date, nullable=False)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    sport_type = Column(String(50), default="Ride")
    distance_km = Column(Numeric(7, 2))
    objective_level = Column(CHAR(1), nullable=False, default="B")
    preparation_notes = Column(Text)
    result_time = Column(Interval)
    result_rank = Column(Integer)
    result_participants = Column(Integer)
    result_distance_km = Column(Numeric(7, 2))
    ressenti = Column(Integer)
    result_notes = Column(Text)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"))
    llm_analysis_id = Column(Integer, ForeignKey("llm_analyses.id", ondelete="SET NULL"))
    created_by = Column(String(50), default="coach")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    athlete_id = Column(Integer, ForeignKey("athlete.id", ondelete="CASCADE"))
    athlete = relationship("Athlete", back_populates="competitions")
    activity = relationship("Activity")
    llm_analysis = relationship("LLMAnalysis", foreign_keys=[llm_analysis_id])

class CoachComment(Base):
    __tablename__ = "coach_comments"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("planned_sessions.id", ondelete="SET NULL"))
    author_role = Column(String(20), nullable=False, default="coach")
    comment = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    athlete_id = Column(Integer, ForeignKey("athlete.id", ondelete="CASCADE"))
    athlete = relationship("Athlete", back_populates="coach_comments")
    activity = relationship("Activity", back_populates="comments")
    session = relationship("PlannedSession", back_populates="comments")

class LLMAnalysis(Base):
    __tablename__ = "llm_analyses"

    id = Column(Integer, primary_key=True, index=True)
    analysis_type = Column(String(50), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    input_payload = Column(JSON, nullable=False)
    prompt_text = Column(Text)
    cached_response = Column(Text, nullable=False)
    model_used = Column(String(100))
    tokens_input = Column(Integer)
    tokens_output = Column(Integer)
    latency_ms = Column(Integer)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
