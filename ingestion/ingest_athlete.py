import os
import re
from dotenv import load_dotenv
from stravalib.client import Client
from sqlalchemy.orm import Session
from db.models import Athlete

load_dotenv()

def parse_zones_string(raw_string):
    """Parse la représentation string d'un objet ZoneRanges.
    Exemple : 'zones=ZoneRanges(root=[ZoneRange(max=130, min=0), ...])'
    Retourne une liste de dicts [{'min': 0, 'max': 130}, ...]"""
    zones_list = []
    # Extraction de toutes les paires max/min
    matches = re.findall(r'ZoneRange\(max=(\d+),\s*min=(\d+)\)', raw_string)
    for max_val, min_val in matches:
        zones_list.append({"min": int(min_val), "max": int(max_val)})
    return zones_list

def upsert_athlete(db: Session):
    client = Client()
    refresh_resp = client.refresh_access_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        refresh_token=os.getenv("STRAVA_REFRESH_TOKEN")
    )
    client.access_token = refresh_resp['access_token']

    athlete_data = client.get_athlete()
    zones_data = client.get_athlete_zones()

    # Récupération des zones sous forme de chaînes (comme dans ls_athlete.py)
    power_raw = str(zones_data.power) if hasattr(zones_data, 'power') and zones_data.power else ""
    hr_raw = str(zones_data.heart_rate) if hasattr(zones_data, 'heart_rate') and zones_data.heart_rate else ""

    # Parsing des chaînes pour obtenir les listes de dicts
    power_zones_list = parse_zones_string(power_raw) if power_raw else []
    hr_zones_list = parse_zones_string(hr_raw) if hr_raw else []

    # Statistiques YTD
    stats = client.get_athlete_stats(athlete_data.id)
    ytd_distance = float(stats.ytd_ride_totals.distance) / 1000 if stats.ytd_ride_totals else 0
    ytd_elev = int(stats.ytd_ride_totals.elevation_gain) if stats.ytd_ride_totals else 0
    ytd_time = float(stats.ytd_ride_totals.moving_time) / 3600 if stats.ytd_ride_totals else 0

    # Upsert athlete
    athlete = db.query(Athlete).filter(Athlete.strava_id == athlete_data.id).first()
    if not athlete:
        athlete = Athlete(strava_id=athlete_data.id)
    athlete.firstname = athlete_data.firstname
    athlete.lastname = athlete_data.lastname
    athlete.city = athlete_data.city
    athlete.country = athlete_data.country
    athlete.profile_pic_url = athlete_data.profile_medium
    athlete.ftp_watts = athlete_data.ftp or 237
    athlete.weight_kg = athlete_data.weight or 71.0
    athlete.power_zones = power_zones_list
    athlete.heart_rate_zones = hr_zones_list
    athlete.ytd_distance_km = ytd_distance
    athlete.ytd_elevation_m = ytd_elev
    athlete.ytd_time_hours = ytd_time
    db.add(athlete)
    db.commit()
    print(f"Athlete {athlete.firstname} {athlete.lastname} synchronisé.")
