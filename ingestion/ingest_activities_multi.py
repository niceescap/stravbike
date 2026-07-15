"""
ingestion/ingest_activities_multi.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Import des activités Strava pour un athlète donné (mode multi-utilisateur).

Contrairement à ingest_activities.py (mono, lit le .env), ce script prend
un athlete_id interne en paramètre et utilise services/strava_client.py
pour obtenir un client Strava authentifié avec le bon refresh token.

Usage :
    python -m ingestion.ingest_activities_multi --athlete-id 3 --limit 50
    python -m ingestion.ingest_activities_multi --athlete-email jean@example.com --limit 50
    python -m ingestion.ingest_activities_multi --all  # tous les athlètes actifs
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Racine du projet dans le path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from stravalib.client import Client
from db.database import SessionLocal
from db.models import Athlete, Activity
from services.strava_client import get_strava_client


# ────────────────────────────────────────────────────────────────────────────
# Calculs métier (IF / TSS)
# ────────────────────────────────────────────────────────────────────────────

def compute_if_tss(
    weighted_avg_watts: Optional[float],
    moving_time_seconds: int,
    ftp_watts: int,
) -> tuple:
    """Calcule IF (Intensity Factor) et TSS (Training Stress Score)."""
    if weighted_avg_watts and ftp_watts and ftp_watts > 0:
        intensity_factor = float(weighted_avg_watts) / ftp_watts
    else:
        intensity_factor = None

    tss = None
    if intensity_factor and moving_time_seconds:
        tss = (
            (moving_time_seconds * float(weighted_avg_watts) * intensity_factor)
            / (ftp_watts * 3600)
            * 100
        )
    return intensity_factor, tss


# ────────────────────────────────────────────────────────────────────────────
# Import historique (N dernières activités)
# ────────────────────────────────────────────────────────────────────────────

def import_historical(
    db: Session,
    athlete: Athlete,
    limit: int = 100,
) -> int:
    """
    Importe les N dernières activités vélo de l'athlète.

    Returns:
        Nombre d'activités importées (nouvelles, pas les doublons).
    """
    strava_client = get_strava_client(db, athlete.id)

    activities = list(strava_client.get_activities(limit=limit))
    cycling_activities = [
        act for act in activities
        if getattr(act, "type", None)
        and getattr(act.type, "root", "") in ("Ride", "VirtualRide")
    ]

    imported = 0
    for act in cycling_activities:
        # Anti-doublon : par (athlete_id, strava_id)
        existing = (
            db.query(Activity)
            .filter(
                Activity.athlete_id == athlete.id,
                Activity.strava_id == act.id,
            )
            .first()
        )
        if existing:
            continue

        # Extraction robuste des champs (gère les objets Duration, etc.)
        act_dict = {k: v for k, v in vars(act).items() if not k.startswith("_")}

        moving_time_s = _to_seconds(act_dict.get("moving_time"))
        elapsed_time_s = _to_seconds(act_dict.get("elapsed_time"))
        distance_m = float(act_dict.get("distance", 0) or 0)
        elevation = float(act_dict.get("total_elevation_gain", 0) or 0)

        avg_watts = act_dict.get("average_watts")
        weighted_avg_watts = act_dict.get("weighted_average_watts")
        max_watts = act_dict.get("max_watts")
        avg_hr = act_dict.get("average_heartrate")
        max_hr = act_dict.get("max_heartrate")
        avg_cadence = act_dict.get("average_cadence")
        kilojoules = act_dict.get("kilojoules")
        suffer_score = act_dict.get("suffer_score")

        # Calculs dérivés
        dist_km = distance_m / 1000.0
        moving_min = moving_time_s / 60.0
        avg_speed = float(act_dict.get("average_speed", 0) or 0)
        speed_kmh = avg_speed * 3.6

        ftp = athlete.ftp_watts or 237
        intensity_factor, tss = compute_if_tss(weighted_avg_watts, moving_time_s, ftp)

        db_act = Activity(
            strava_id=act.id,
            name=act_dict.get("name"),
            sport_type=getattr(act.type, "root", None),
            start_date=act.start_date,
            start_date_local=act.start_date_local,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elapsed_time_s=elapsed_time_s,
            elevation_gain_m=elevation,
            avg_watts=avg_watts,
            weighted_avg_watts=weighted_avg_watts,
            max_watts=max_watts,
            avg_heartrate=avg_hr,
            max_heartrate=max_hr,
            avg_cadence=avg_cadence,
            kilojoules=kilojoules,
            suffer_score=suffer_score,
            distance_km=dist_km,
            moving_time_min=moving_min,
            avg_speed_kmh=speed_kmh,
            intensity_factor=intensity_factor,
            tss=tss,
            streams_json=None,  # Récupéré ultérieurement si besoin
            athlete_id=athlete.id,
        )
        db.add(db_act)
        imported += 1

    db.commit()
    return imported


# ────────────────────────────────────────────────────────────────────────────
# Import incrémental (depuis la dernière activité connue)
# ────────────────────────────────────────────────────────────────────────────

def incremental_refresh(
    db: Session,
    athlete: Athlete,
) -> int:
    """
    Importe les activités postérieures à la dernière connue.

    Returns:
        Nombre de nouvelles activités importées.
    """
    strava_client = get_strava_client(db, athlete.id)

    # Dernière activité connue
    last_activity = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete.id)
        .order_by(Activity.start_date.desc())
        .first()
    )
    after_datetime = last_activity.start_date if last_activity else None

    activities = list(strava_client.get_activities(limit=200, after=after_datetime))
    cycling_activities = [
        act for act in activities
        if getattr(act, "type", None)
        and getattr(act.type, "root", "") in ("Ride", "VirtualRide")
    ]

    imported = 0
    for act in cycling_activities:
        existing = (
            db.query(Activity)
            .filter(
                Activity.athlete_id == athlete.id,
                Activity.strava_id == act.id,
            )
            .first()
        )
        if existing:
            continue

        act_dict = {k: v for k, v in vars(act).items() if not k.startswith("_")}

        moving_time_s = _to_seconds(act_dict.get("moving_time"))
        elapsed_time_s = _to_seconds(act_dict.get("elapsed_time"))
        distance_m = float(act_dict.get("distance", 0) or 0)
        elevation = float(act_dict.get("total_elevation_gain", 0) or 0)

        avg_watts = act_dict.get("average_watts")
        weighted_avg_watts = act_dict.get("weighted_average_watts")
        max_watts = act_dict.get("max_watts")
        avg_hr = act_dict.get("average_heartrate")
        max_hr = act_dict.get("max_heartrate")
        avg_cadence = act_dict.get("average_cadence")
        kilojoules = act_dict.get("kilojoules")
        suffer_score = act_dict.get("suffer_score")

        dist_km = distance_m / 1000.0
        moving_min = moving_time_s / 60.0
        avg_speed = float(act_dict.get("average_speed", 0) or 0)
        speed_kmh = avg_speed * 3.6

        ftp = athlete.ftp_watts or 237
        intensity_factor, tss = compute_if_tss(weighted_avg_watts, moving_time_s, ftp)

        db_act = Activity(
            strava_id=act.id,
            name=act_dict.get("name"),
            sport_type=getattr(act.type, "root", None),
            start_date=act.start_date,
            start_date_local=act.start_date_local,
            distance_m=distance_m,
            moving_time_s=moving_time_s,
            elapsed_time_s=elapsed_time_s,
            elevation_gain_m=elevation,
            avg_watts=avg_watts,
            weighted_avg_watts=weighted_avg_watts,
            max_watts=max_watts,
            avg_heartrate=avg_hr,
            max_heartrate=max_hr,
            avg_cadence=avg_cadence,
            kilojoules=kilojoules,
            suffer_score=suffer_score,
            distance_km=dist_km,
            moving_time_min=moving_min,
            avg_speed_kmh=speed_kmh,
            intensity_factor=intensity_factor,
            tss=tss,
            streams_json=None,
            athlete_id=athlete.id,
        )
        db.add(db_act)
        imported += 1

    db.commit()
    return imported


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _to_seconds(value) -> int:
    """Convertit une valeur Duration ou int en secondes."""
    if value is None:
        return 0
    if hasattr(value, "seconds"):
        return int(value.seconds)
    return int(value or 0)


def _get_athlete_by_email(db: Session, email: str) -> Optional[Athlete]:
    """Récupère le premier athlète appartenant à l'utilisateur avec cet email."""
    from db.models import User

    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    return (
        db.query(Athlete)
        .filter(Athlete.owner_user_id == user.id, Athlete.is_active == True)
        .first()
    )


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée CLI
# ────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import activités Strava (multi-user)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--athlete-id", type=int, help="ID interne de l'athlète")
    group.add_argument(
        "--athlete-email", type=str, help="Email de l'utilisateur propriétaire"
    )
    group.add_argument("--all", action="store_true", help="Tous les athlètes actifs")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Nombre max d'activités à importer (défaut: 100)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Mode incrémental (depuis dernière activité connue)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    total_imported = 0

    try:
        if args.all:
            athletes = db.query(Athlete).filter(Athlete.is_active == True).all()
            if not athletes:
                print("❌ Aucun athlète actif trouvé.")
                return
            print(f"🔄 Traitement de {len(athletes)} athlète(s)...")
        elif args.athlete_email:
            athlete = _get_athlete_by_email(db, args.athlete_email)
            if not athlete:
                print(f"❌ Aucun athlète trouvé pour l'email {args.athlete_email}")
                return
            athletes = [athlete]
        else:
            athlete = db.query(Athlete).filter(Athlete.id == args.athlete_id).first()
            if not athlete:
                print(f"❌ Athlète ID {args.athlete_id} introuvable.")
                return
            athletes = [athlete]

        for athlete in athletes:
            name = f"{athlete.firstname} {athlete.lastname}".strip()
            print(f"\n{'='*60}")
            print(f"🚴 {name} (Strava ID: {athlete.strava_id})")
            print(f"{'='*60}")

            try:
                if args.incremental:
                    count = incremental_refresh(db, athlete)
                else:
                    count = import_historical(db, athlete, limit=args.limit)
                total_imported += count
                print(f"✅ {count} activité(s) importée(s).")
            except Exception as exc:
                print(f"❌ Erreur pour {name}: {exc}")

    finally:
        db.close()

    print(f"\n{'='*60}")
    print(f"📊 Total: {total_imported} activité(s) importée(s).")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
