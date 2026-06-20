import os
import json
from dotenv import load_dotenv
from stravalib.client import Client

# 1. On charge le .env mis à jour par le script du gars
load_dotenv()

client = Client()

print("=== Tentative de connexion avec le nouveau Refresh Token ===")

try:
    # On utilise le Refresh Token qui a maintenant le scope "activity:read"
    response = client.refresh_access_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        refresh_token=os.getenv("STRAVA_REFRESH_TOKEN")
    )
    # On applique le nouveau jeton d'accès généré à la volée
    client.access_token = response['access_token']
    print("=== Connexion Strava OK ! ===")

    # 2. Le "ls" de l'API
    activities = list(client.get_activities(limit=1))
    if not activities:
        print("Connexion réussie, mais aucune activité trouvée sur ce compte.")
        exit()
        
    last_activity = activities[0]
    print(f"\n--- SCANNER DE L'ACTIVITÉ : {last_activity.name} (ID: {last_activity.id}) ---")
    
    try:
        activity_dict = last_activity.to_dict()
    except AttributeError:
        activity_dict = {k: v for k, v in vars(last_activity).items() if not k.startswith('_')}

    # Affichage propre du catalogue JSON
    print(json.dumps(activity_dict, indent=4, default=str, ensure_ascii=False))

except Exception as e:
    print(f"Erreur : {e}")
