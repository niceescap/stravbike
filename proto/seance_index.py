import os
import sys
import json
from dotenv import load_dotenv
from stravalib.client import Client

load_dotenv()
client = Client()

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0

EXCLUDE_KEYS = {"map", "segment_efforts", "splits_metric", "splits_standard", "laps", "best_efforts"}

def summarize_map(activity):
    """Extrait un point GPS barycentre depuis start_latlng / end_latlng."""
    try:
        start = activity.start_latlng
        end = activity.end_latlng
        if start and end:
            lat = (start.lat + end.lat) / 2
            lng = (start.lon + end.lon) / 2
            return {"barycentre_approx": {"lat": round(lat, 5), "lng": round(lng, 5)}}
        elif start:
            return {"start_only": {"lat": round(start.lat, 5), "lng": round(start.lon, 5)}}
    except Exception:
        pass
    return {"gps": None}

try:
    response = client.refresh_access_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        refresh_token=os.getenv("STRAVA_REFRESH_TOKEN")
    )
    client.access_token = response['access_token']

    activities = list(client.get_activities(limit=idx + 1))
    if not activities or idx >= len(activities):
        print(f"Pas d'activité à l'index {idx}")
        exit()

    target = activities[idx]
    print(f"\n--- ACTIVITÉ [{idx}] : {target.name} (ID: {target.id}) ---\n")

    try:
        raw = target.to_dict()
    except AttributeError:
        raw = {k: v for k, v in vars(target).items() if not k.startswith('_')}

    # Nettoyage + remplacement map
    cleaned = {k: v for k, v in raw.items() if k not in EXCLUDE_KEYS}
    cleaned["map"] = summarize_map(target)

    print(json.dumps(cleaned, indent=4, default=str, ensure_ascii=False))

except Exception as e:
    print(f"Erreur : {e}")
