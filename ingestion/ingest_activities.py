import os
from dotenv import load_dotenv
from stravalib.client import Client
from sqlalchemy.orm import Session
from db.models import Athlete, Activity

load_dotenv()

client = Client()

def get_strava_client() -> Client:
    refresh_resp = client.refresh_access_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        refresh_token=os.getenv("STRAVA_REFRESH_TOKEN")
    )
    client.access_token = refresh_resp['access_token']
    return client

def compute_if_tss(weighted_avg_watts, moving_time_seconds, ftp_watts):
    """Calcule IF et TSS à partir de valeurs numériques simples."""
    if weighted_avg_watts and ftp_watts and ftp_watts > 0:
        intensity_factor = float(weighted_avg_watts) / ftp_watts
    else:
        intensity_factor = None
    tss = None
    if intensity_factor and moving_time_seconds:
        tss = (moving_time_seconds * float(weighted_avg_watts) * intensity_factor) / (ftp_watts * 3600) * 100
    return intensity_factor, tss

def import_historical(db: Session, athlete_id: int, limit: int = 100):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise ValueError("Athlète non trouvé")
    strava_client = get_strava_client()

    # Récupère les N dernières activités (Strava renvoie par date décroissante)
    activities = list(strava_client.get_activities(limit=limit))
    cycling_activities = [act for act in activities if act.type.root in ('Ride', 'VirtualRide')]

    imported = 0
    for act in cycling_activities:
        if db.query(Activity).filter(Activity.strava_id == act.id).first():
            continue

        # Méthode fiable du test_data.py : vars() sans attributs privés
        act_dict = {k: v for k, v in vars(act).items() if not k.startswith('_')}

        # Extraction des valeurs numériques (gère automatiquement les entiers/Duration)
        moving_time_s = act_dict.get('moving_time', 0)
        if hasattr(moving_time_s, 'seconds'):
            moving_time_s = moving_time_s.seconds
        else:
            moving_time_s = int(moving_time_s or 0)

        elapsed_time_s = act_dict.get('elapsed_time', 0)
        if hasattr(elapsed_time_s, 'seconds'):
            elapsed_time_s = elapsed_time_s.seconds
        else:
            elapsed_time_s = int(elapsed_time_s or 0)

        distance_m = float(act_dict.get('distance', 0) or 0)
        avg_speed = float(act_dict.get('average_speed', 0) or 0)
        avg_watts = act_dict.get('average_watts')
        weighted_avg_watts = act_dict.get('weighted_average_watts')
        avg_hr = act_dict.get('average_heartrate')
        max_hr = act_dict.get('max_heartrate')
        max_watts = act_dict.get('max_watts')
        avg_cadence = act_dict.get('average_cadence')
        kilojoules = act_dict.get('kilojoules')
        suffer_score = act_dict.get('suffer_score')
        elevation = act_dict.get('total_elevation_gain')

        # Calculs dérivés
        dist_km = distance_m / 1000.0
        moving_min = moving_time_s / 60.0
        speed_kmh = avg_speed * 3.6

        intensity_factor, tss = compute_if_tss(weighted_avg_watts, moving_time_s, athlete.ftp_watts)

        db_act = Activity(
            strava_id=act.id,
            name=act_dict.get('name'),
            sport_type=act.type.root,
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
            streams_json=None,   # à récupérer plus tard si nécessaire
            athlete_id=athlete.id
        )
        db.add(db_act)
        imported += 1

    db.commit()
    print(f"✅ Import historique terminé : {imported} activités vélo importées (sur les {limit} dernières).")

def incremental_refresh(db: Session, athlete_id: int):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise ValueError("Athlète non trouvé")
    strava_client = get_strava_client()

    # Dernière activité connue
    last_activity = db.query(Activity)\
        .filter(Activity.athlete_id == athlete.id)\
        .order_by(Activity.start_date.desc())\
        .first()

    after_datetime = last_activity.start_date if last_activity else None

    # Récupère les activités postérieures (after accepte un datetime)
    activities = list(strava_client.get_activities(limit=200, after=after_datetime))
    cycling_activities = [act for act in activities if act.type.root in ('Ride', 'VirtualRide')]

    # ... la suite de la boucle d'insertion reste inchangée
    imported = 0
    for act in cycling_activities:
        if db.query(Activity).filter(Activity.strava_id == act.id).first():
            continue

        # Même conversion robuste que dans import_historical
        act_dict = {k: v for k, v in vars(act).items() if not k.startswith('_')}

        moving_time_s = act_dict.get('moving_time', 0)
        if hasattr(moving_time_s, 'seconds'):
            moving_time_s = moving_time_s.seconds
        else:
            moving_time_s = int(moving_time_s or 0)

        elapsed_time_s = act_dict.get('elapsed_time', 0)
        if hasattr(elapsed_time_s, 'seconds'):
            elapsed_time_s = elapsed_time_s.seconds
        else:
            elapsed_time_s = int(elapsed_time_s or 0)

        distance_m = float(act_dict.get('distance', 0) or 0)
        avg_speed = float(act_dict.get('average_speed', 0) or 0)
        weighted_avg_watts = act_dict.get('weighted_average_watts')
        avg_watts = act_dict.get('average_watts')
        avg_hr = act_dict.get('average_heartrate')
        max_hr = act_dict.get('max_heartrate')
        max_watts = act_dict.get('max_watts')
        avg_cadence = act_dict.get('average_cadence')
        kilojoules = act_dict.get('kilojoules')
        suffer_score = act_dict.get('suffer_score')
        elevation = act_dict.get('total_elevation_gain')

        dist_km = distance_m / 1000.0
        moving_min = moving_time_s / 60.0
        speed_kmh = avg_speed * 3.6

        intensity_factor, tss = compute_if_tss(weighted_avg_watts, moving_time_s, athlete.ftp_watts)

        db_act = Activity(
            strava_id=act.id,
            name=act_dict.get('name'),
            sport_type=act.type.root,
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
            athlete_id=athlete.id
        )
        db.add(db_act)
        imported += 1

    db.commit()
    print(f"✅ Import incrémental terminé : {imported} nouvelle(s) activité(s) vélo.")
