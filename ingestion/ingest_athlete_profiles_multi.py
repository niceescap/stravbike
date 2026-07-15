"""
ingestion/ingest_athlete_profiles_multi.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Synchronisation des profils Strava (FTP, poids, zones) pour un athlète donné.

Utilise l'API Strava pour récupérer :
  - Le profil athlète (nom, ville, poids, FTP)
  - Les zones de puissance et de fréquence cardiaque
  - Les statistiques YTD (distance, dénivelé, temps)

Contrairement à ingest_athlete.py (mono), ce script prend un athlete_id
interne et utilise services/strava_client.py pour s'authentifier.

Usage :
    python -m ingestion.ingest_athlete_profiles_multi --athlete-id 3
    python -m ingestion.ingest_athlete_profiles_multi --athlete-email jean@example.com
    python -m ingestion.ingest_athlete_profiles_multi --all
"""

import sys
import re
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from sqlalchemy.orm import Session
from stravalib.client import Client
from db.database import SessionLocal
from db.models import Athlete
from services.strava_client import get_strava_client


# ────────────────────────────────────────────────────────────────────────────
# Parsing des zones (format string Stravalib)
# ────────────────────────────────────────────────────────────────────────────

def parse_zones_string(raw_string: str) -> List[dict]:
    """
    Parse la représentation string d'un objet ZoneRanges Stravalib.

    Exemple d'entrée :
        'zones=ZoneRanges(root=[ZoneRange(max=130, min=0), ...])'

    Retourne :
        [{"min": 0, "max": 130}, {"min": 130, "max": 156}, ...]
    """
    zones_list = []
    matches = re.findall(r"ZoneRange\(max=(\d+),\s*min=(\d+)\)", raw_string)
    for max_val, min_val in matches:
        zones_list.append({"min": int(min_val), "max": int(max_val)})
    return zones_list


# ────────────────────────────────────────────────────────────────────────────
# UPSERT du profil athlète
# ────────────────────────────────────────────────────────────────────────────

def upsert_athlete_profile(db: Session, athlete: Athlete) -> dict:
    """
    Met à jour le profil Strava d'un athlète (en DB) depuis l'API Strava.

    Récupère :
      - Identité (nom, ville, pays, avatar)
      - FTP et poids
      - Zones de puissance et FC
      - Stats YTD

    Returns:
        Dict avec les stats YTD et le nombre de champs mis à jour.
    """
    strava_client = get_strava_client(db, athlete.id)

    # ── 1. Profil athlète ──────────────────────────────────────────────────
    athlete_data = strava_client.get_athlete()

    updates = {}
    if athlete_data.firstname and athlete.firstname != athlete_data.firstname:
        athlete.firstname = athlete_data.firstname
        updates["firstname"] = athlete_data.firstname
    if athlete_data.lastname and athlete.lastname != athlete_data.lastname:
        athlete.lastname = athlete_data.lastname
        updates["lastname"] = athlete_data.lastname
    if athlete_data.city and athlete.city != athlete_data.city:
        athlete.city = athlete_data.city
        updates["city"] = athlete_data.city
    if athlete_data.country and athlete.country != athlete_data.country:
        athlete.country = athlete_data.country
        updates["country"] = athlete_data.country
    if athlete_data.profile_medium and athlete.profile_pic_url != athlete_data.profile_medium:
        athlete.profile_pic_url = athlete_data.profile_medium
        updates["profile_pic_url"] = athlete_data.profile_medium

    # FTP (peut être None)
    if athlete_data.ftp is not None and athlete.ftp_watts != athlete_data.ftp:
        athlete.ftp_watts = int(athlete_data.ftp)
        updates["ftp_watts"] = athlete_data.ftp

    # Poids (peut être None)
    if athlete_data.weight is not None and float(athlete.weight_kg or 0) != float(athlete_data.weight):
        athlete.weight_kg = float(athlete_data.weight)
        updates["weight_kg"] = athlete_data.weight

    # ── 2. Zones ───────────────────────────────────────────────────────────
    zones_data = strava_client.get_athlete_zones()

    # Zones de puissance
    power_raw = (
        str(zones_data.power)
        if hasattr(zones_data, "power") and zones_data.power
        else ""
    )
    power_zones = parse_zones_string(power_raw) if power_raw else []
    if power_zones and athlete.power_zones != power_zones:
        athlete.power_zones = power_zones
        updates["power_zones"] = f"{len(power_zones)} zones"

    # Zones de FC
    hr_raw = (
        str(zones_data.heart_rate)
        if hasattr(zones_data, "heart_rate") and zones_data.heart_rate
        else ""
    )
    hr_zones = parse_zones_string(hr_raw) if hr_raw else []
    if hr_zones and athlete.heart_rate_zones != hr_zones:
        athlete.heart_rate_zones = hr_zones
        updates["heart_rate_zones"] = f"{len(hr_zones)} zones"

    # ── 3. Stats YTD ───────────────────────────────────────────────────────
    try:
        stats = strava_client.get_athlete_stats(athlete.strava_id)
        if stats.ytd_ride_totals:
            ytd_distance = float(stats.ytd_ride_totals.distance) / 1000  # m → km
            ytd_elev = int(stats.ytd_ride_totals.elevation_gain)
            ytd_time = float(stats.ytd_ride_totals.moving_time) / 3600  # s → h

            if athlete.ytd_distance_km != ytd_distance:
                athlete.ytd_distance_km = ytd_distance
                updates["ytd_distance_km"] = ytd_distance
            if athlete.ytd_elevation_m != ytd_elev:
                athlete.ytd_elevation_m = ytd_elev
                updates["ytd_elevation_m"] = ytd_elev
            if athlete.ytd_time_hours != ytd_time:
                athlete.ytd_time_hours = ytd_time
                updates["ytd_time_hours"] = ytd_time
    except Exception as exc:
        print(f"  ⚠ Stats YTD non disponibles: {exc}")

    db.commit()
    return updates


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _get_athlete_by_email(db: Session, email: str) -> Optional[Athlete]:
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
    parser = argparse.ArgumentParser(
        description="Synchronisation profils Strava (multi-user)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--athlete-id", type=int, help="ID interne de l'athlète")
    group.add_argument(
        "--athlete-email", type=str, help="Email du propriétaire de l'athlète"
    )
    group.add_argument("--all", action="store_true", help="Tous les athlètes actifs")
    args = parser.parse_args()

    db = SessionLocal()
    results = []

    try:
        if args.all:
            athletes = db.query(Athlete).filter(Athlete.is_active == True).all()
            if not athletes:
                print("❌ Aucun athlète actif trouvé.")
                return
            print(f"🔄 Synchronisation de {len(athletes)} athlète(s)...")
        elif args.athlete_email:
            athlete = _get_athlete_by_email(db, args.athlete_email)
            if not athlete:
                print(f"❌ Aucun athlète trouvé pour {args.athlete_email}")
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
            print(f"👤 {name} (Strava ID: {athlete.strava_id})")
            print(f"{'='*60}")

            try:
                updates = upsert_athlete_profile(db, athlete)
                if updates:
                    print(f"✅ Profil mis à jour :")
                    for key, val in updates.items():
                        print(f"   • {key}: {val}")
                else:
                    print("♻️ Profil inchangé (déjà à jour).")
                results.append((name, True, None))
            except Exception as exc:
                print(f"❌ Erreur: {exc}")
                results.append((name, False, str(exc)))

    finally:
        db.close()

    # Rapport
    print(f"\n{'='*60}")
    success = sum(1 for _, ok, _ in results if ok)
    print(f"📊 {success}/{len(results)} athlète(s) synchronisé(s).")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
