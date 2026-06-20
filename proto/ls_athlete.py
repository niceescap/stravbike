import os
import json
from dotenv import load_dotenv
from stravalib.client import Client

load_dotenv()
client = Client()

try:
    # --- ÉTAPE A ---
    response = client.refresh_access_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        refresh_token=os.getenv("STRAVA_REFRESH_TOKEN")
    )
    client.access_token = response['access_token']
    
    print("=== CONFIGURATION ET RECHERCHE ATHLÈTE ===")

    # --- ÉTAPE B ---
    athlete = client.get_athlete()
    print(f"\nProfil de l'athlète :")
    print(f"ID : {athlete.id}")
    print(f"Prénom : {athlete.firstname}")
    print(f"Nom : {athlete.lastname}")
    print(f"Poids configuré : {athlete.weight} kg")
    print(f"FTP configuré : {getattr(athlete, 'ftp', 'Non défini')} W")

    # --- ÉTAPE C (Version d'origine intacte) ---
    print("\n--- Zones de l'Athlète (Cardio / Puissance) ---")
    zones = client.get_athlete_zones()
    
    print("Données brutes Puissance (Power) :")
    print(zones.power if hasattr(zones, 'power') else "Non disponible")
    
    print("\nDonnées brutes Cardio (Heart Rate) :")
    print(zones.heart_rate if hasattr(zones, 'heart_rate') else "Non disponible")

    # --- ÉTAPE D ---
    print("\n--- Volumes Globaux (Statistiques) ---")
    stats = client.get_athlete_stats(athlete.id)
    
    print("\n[Année en cours - Cyclisme]")
    if stats.ytd_ride_totals:
        print(f"  Nombre de sorties : {stats.ytd_ride_totals.count}")
        print(f"  Distance totale   : {stats.ytd_ride_totals.distance / 1000:.1f} km")
        print(f"  Temps de selle    : {stats.ytd_ride_totals.moving_time / 3600:.1f} heures")
        print(f"  Dénivelé positif  : {stats.ytd_ride_totals.elevation_gain:.0f} m")

    print("\n[Historique Global - Cyclisme]")
    if stats.all_ride_totals:
        print(f"  Nombre de sorties : {stats.all_ride_totals.count}")
        print(f"  Distance totale   : {stats.all_ride_totals.distance / 1000:.1f} km")
        print(f"  Temps de selle    : {stats.all_ride_totals.moving_time / 3600:.1f} heures")

    print("\n[4 Dernières Semaines - Cyclisme]")
    if stats.recent_ride_totals:
        print(f"  Nombre de sorties : {stats.recent_ride_totals.count}")
        print(f"  Distance totale   : {stats.recent_ride_totals.distance / 1000:.1f} km")

    # ==============================================================================
    # SAUVEGARDE SÉCURISÉE EN CHAÎNE DE CARACTÈRES BRUTE
    # ==============================================================================
    master_data = {
        "athlete_id": athlete.id,
        "nom": athlete.lastname,
        "prenom": athlete.firstname,
        "poids_athlete": athlete.weight if athlete.weight else 71.0,
        "ftp_config": getattr(athlete, 'ftp', 237) if getattr(athlete, 'ftp', 237) else 237,
        "raw_power_string": str(zones.power),
        "raw_hr_string": str(zones.heart_rate)
    }

    with open("strava_athlete_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)
        
    print("\n💾 Sauvegarde brute effectuée dans strava_athlete_data.json.")

except Exception as e:
    print(f"\n❌ Erreur générale : {e}")
