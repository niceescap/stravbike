import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///strava_coach")

connect_args = {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Crée les tables via SQLAlchemy (idempotent) et la vue calendar_view."""
    from db.models import Base
    Base.metadata.create_all(bind=engine)  # crée les tables si absentes, ignore les existantes
    # Création de la vue (indépendante, on utilise CREATE OR REPLACE)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW calendar_view AS
            SELECT
                COALESCE(ps.session_date, a.start_date_local::DATE, c.competition_date) AS calendar_date,
                ps.id AS session_id,
                ps.title AS session_title,
                ps.description AS session_description,
                ps.status AS session_status,
                ps.validated AS session_validated,
                ps.ressenti AS session_ressenti,
                a.id AS activity_id,
                a.name AS activity_name,
                a.moving_time_min,
                a.weighted_avg_watts,
                a.avg_heartrate,
                a.tss,
                a.intensity_factor,
                c.id AS competition_id,
                c.name AS competition_name,
                c.objective_level,
                c.result_rank,
                CASE
                    WHEN c.id IS NOT NULL THEN '🏆'
                    WHEN ps.validated = TRUE THEN '✅'
                    WHEN ps.validated = FALSE THEN '❌'
                    WHEN ps.id IS NOT NULL AND a.id IS NULL AND ps.session_date < CURRENT_DATE THEN '❌'
                    WHEN ps.id IS NOT NULL AND a.id IS NULL THEN '⏳'
                    WHEN a.id IS NOT NULL AND ps.id IS NULL THEN '🚴'
                    ELSE '⬜'
                END AS badge
            FROM planned_sessions ps
                FULL OUTER JOIN activities a ON a.start_date_local::DATE = ps.session_date AND ps.activity_id = a.id
                FULL OUTER JOIN competitions c ON c.competition_date = COALESCE(ps.session_date, a.start_date_local::DATE);
        """))
        conn.commit()
    print("Base de données initialisée.")
