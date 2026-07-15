from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, Text, DateTime, Date, ForeignKey, JSON, Interval, CHAR, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================================================
# TABLE 1 — User (authentification système)
# ============================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Identité système
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255))  # bcrypt/argon2, NULL si auth externe
    firstname = Column(String(100))
    lastname = Column(String(100))

    # Magic link (optionnel, pour partager accès)
    magic_link_token = Column(String(64), unique=True, nullable=True)
    magic_link_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relations
    athletes = relationship("Athlete", back_populates="owner", cascade="all, delete-orphan")
    shared_athletes = relationship(
        "AthleteSharing",
        back_populates="shared_with_user",
        foreign_keys="[AthleteSharing.shared_with_user_id]",
        cascade="all, delete-orphan",
    )
    comments = relationship("Comment", back_populates="user")


# ============================================================================
# TABLE 2 — Athlete (profil Strava, multi-athlète)
# ============================================================================
class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, index=True)

    # Identité Strava (pas unique — plusieurs users peuvent référencer un athlète)
    strava_id = Column(BigInteger, nullable=False, index=True)
    firstname = Column(String(100))
    lastname = Column(String(100))
    city = Column(String(100))
    country = Column(String(100))
    profile_pic_url = Column(Text)

    # Propriété
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("User", back_populates="athletes")

    # Token Strava (stocké ici au lieu de fichiers JSON)
    strava_refresh_token = Column(String(255), nullable=True)  # À chiffrer en prod
    strava_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Constantes d'entraînement
    ftp_watts = Column(Integer, default=237)
    weight_kg = Column(Numeric(5, 2), default=71.0)
    power_zones = Column(JSON)  # [{"min": 0, "max": 115}, ...]
    heart_rate_zones = Column(JSON)

    # Stats YTD
    ytd_distance_km = Column(Numeric(8, 2))
    ytd_elevation_m = Column(Integer)
    ytd_time_hours = Column(Numeric(6, 2))

    # Visibilité (flexible pour futur)
    visibility = Column(String(20), default="private")  # 'private', 'public', 'friends_only'
    is_active = Column(Boolean, default=True)

    # Métadonnées
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    activities = relationship("Activity", back_populates="athlete", cascade="all, delete-orphan")
    planned_sessions = relationship("PlannedSession", back_populates="athlete", cascade="all, delete-orphan")
    competitions = relationship("Competition", back_populates="athlete", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="athlete", cascade="all, delete-orphan")
    llm_analyses = relationship("LLMAnalysis", back_populates="athlete", cascade="all, delete-orphan")


# ============================================================================
# TABLE 3 — AthleteSharing (partage d'accès futur)
# ============================================================================
class AthleteSharing(Base):
    __tablename__ = "athlete_sharing"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    magic_link_token = Column(String(64), unique=True, nullable=True)
    magic_link_expires_at = Column(DateTime(timezone=True), nullable=True)
    can_view = Column(Boolean, default=True)
    can_comment = Column(Boolean, default=True)
    can_create_sessions = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relations
    athlete = relationship("Athlete")
    shared_with_user = relationship(
        "User",
        back_populates="shared_athletes",
        foreign_keys=[shared_with_user_id],
    )


# ============================================================================
# TABLE 4 — Activity (activités Strava)
# ============================================================================
class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)

    # Clé Strava (unique par athlète, pas globally unique)
    strava_id = Column(BigInteger, nullable=False, index=True)

    # Propriété
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete = relationship("Athlete", back_populates="activities")

    # Données brutes Strava
    name = Column(String(255))
    sport_type = Column(String(50))
    start_date = Column(DateTime(timezone=True))
    start_date_local = Column(DateTime(timezone=True), index=True)

    # Métriques brutes
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

    # Colonnes calculées
    distance_km = Column(Numeric(8, 3))
    moving_time_min = Column(Numeric(8, 2))
    avg_speed_kmh = Column(Numeric(6, 2))
    intensity_factor = Column(Numeric(5, 3))
    tss = Column(Numeric(8, 2))

    # Streams (graphiques)
    streams_json = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relations
    comments = relationship("Comment", back_populates="activity", cascade="all, delete-orphan")
    sessions = relationship("PlannedSession", back_populates="activity")

    # Anti-doublon au niveau athlète
    __table_args__ = (
        UniqueConstraint('athlete_id', 'strava_id', name='uq_athlete_strava_id'),
    )


# ============================================================================
# TABLE 5 — PlannedSession (séances planifiées)
# ============================================================================
class PlannedSession(Base):
    __tablename__ = "planned_sessions"

    id = Column(Integer, primary_key=True, index=True)

    # Propriété
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete = relationship("Athlete", back_populates="planned_sessions")

    # Contenu
    session_date = Column(Date, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    sport_type = Column(String(50), default="Ride")

    # Cibles métriques
    target_duration_min = Column(Integer)
    target_tss = Column(Numeric(6, 2))
    target_if_min = Column(Numeric(4, 3))
    target_if_max = Column(Numeric(4, 3))
    target_distance_km = Column(Numeric(7, 2))

    # Statut
    status = Column(String(20), default="planned")  # planned, completed, missed, cancelled
    validated = Column(Boolean)
    validation_score = Column(Numeric(5, 2))
    validation_detail = Column(JSON)

    # Lien vers activité réalisée
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True)
    activity = relationship("Activity", back_populates="sessions")

    # Ressenti athlète
    ressenti = Column(Integer)  # 1-5
    fatigue = Column(Integer)   # 1-5
    athlete_comment = Column(Text)

    # Métadonnées
    created_by = Column(String(50), default="coach")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    comments = relationship("Comment", back_populates="session", cascade="all, delete-orphan")


# ============================================================================
# TABLE 6 — Competition (objectifs course)
# ============================================================================
class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True, index=True)

    # Propriété
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete = relationship("Athlete", back_populates="competitions")

    # Contenu
    competition_date = Column(Date, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    sport_type = Column(String(50), default="Ride")
    distance_km = Column(Numeric(7, 2))

    # Niveau d'objectif
    objective_level = Column(CHAR(1), nullable=False, default="B")  # A, B, C

    # Préparation
    preparation_notes = Column(Text)

    # Résultat (saisi après la course)
    result_time = Column(Interval)
    result_rank = Column(Integer)
    result_participants = Column(Integer)
    result_distance_km = Column(Numeric(7, 2))
    ressenti = Column(Integer)  # 1-5
    result_notes = Column(Text)

    # Liens
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True)
    activity = relationship("Activity")
    llm_analysis_id = Column(Integer, ForeignKey("llm_analyses.id", ondelete="SET NULL"), nullable=True)

    # Métadonnées
    created_by = Column(String(50), default="coach")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ============================================================================
# TABLE 7 — Comment (commentaires authentifiés)
# ============================================================================
class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)

    # Propriété de l'athlète
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete = relationship("Athlete", back_populates="comments")

    # Auteur (utilisateur authentifié)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user = relationship("User", back_populates="comments")

    # Sur quoi porte le commentaire ?
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True)
    activity = relationship("Activity", back_populates="comments")

    session_id = Column(Integer, ForeignKey("planned_sessions.id", ondelete="SET NULL"), nullable=True)
    session = relationship("PlannedSession", back_populates="comments")

    # Contenu
    comment = Column(Text, nullable=False)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ============================================================================
# TABLE 8 — LLMAnalysis (cache des réponses LLM)
# ============================================================================
class LLMAnalysis(Base):
    __tablename__ = "llm_analyses"

    id = Column(Integer, primary_key=True, index=True)

    # Propriété
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete = relationship("Athlete", back_populates="llm_analyses")

    # Type d'analyse
    analysis_type = Column(String(50), nullable=False)
    entity_type = Column(String(50))  # 'activity', 'session', 'competition'
    entity_id = Column(Integer)

    # Payload & réponse
    input_payload = Column(JSON, nullable=False)
    prompt_text = Column(Text)
    cached_response = Column(Text, nullable=False)

    # Metadata de l'appel
    model_used = Column(String(100))
    tokens_input = Column(Integer)
    tokens_output = Column(Integer)
    latency_ms = Column(Integer)

    # Durée de validité du cache
    expires_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
