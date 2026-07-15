import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Charge les variables d'environnement
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

# DATABASE_URL doit pointer vers db_multi_stravbike
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///db_multi_stravbike")

connect_args = {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency pour FastAPI — une session par request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crée les tables via SQLAlchemy (idempotent) + vue calendar_view.

    À exécuter au startup de l'app pour initialiser la DB.
    """
    from db.models import Base

    # Crée toutes les tables si absentes
    Base.metadata.create_all(bind=engine)

    # Crée la vue calendar_view (refactorisée pour multi-athlète)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW calendar_view AS
            SELECT
                ath.id AS athlete_id,
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
            FROM athletes ath
                LEFT JOIN planned_sessions ps ON ps.athlete_id = ath.id
                LEFT JOIN activities a ON a.athlete_id = ath.id
                    AND a.start_date_local::DATE = ps.session_date
                    AND ps.activity_id = a.id
                LEFT JOIN competitions c ON c.athlete_id = ath.id
                    AND c.competition_date = COALESCE(ps.session_date, a.start_date_local::DATE);
        """))
        conn.commit()

    print("✅ Base de données db_multi_stravbike initialisée (multi-athlète).")
