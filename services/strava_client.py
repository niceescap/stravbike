"""
services/strava_client.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Fabrique de clients Strava multi-athlètes.

Remplace l'ancien get_strava_client() mono-utilisateur qui lisait un
refresh token figé dans le .env. Ici, chaque appel reçoit un athlete_id
et charge dynamiquement les credentials depuis la table athletes.

Usage :
    from services.strava_client import get_strava_client
    client = get_strava_client(db, athlete_id)
    athlete_data = client.get_athlete()
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from stravalib.client import Client
from sqlalchemy.orm import Session

# Charge .env (chemin relatif à la racine du projet)
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")

# Délai de sécurité : on refresh 5 min avant l'expiration officielle
REFRESH_BUFFER = timedelta(minutes=5)


class StravaTokenExpired(Exception):
    """Le refresh a échoué — le token de l'athlète est invalide ou révoqué."""
    pass


def get_strava_client(db: Session, athlete_id: int) -> Client:
    """
    Crée un client Strava authentifié pour un athlète donné.

    Gère automatiquement le refresh du token si l'access_token est expiré
    (ou va l'être dans moins de 5 minutes).

    Args:
        db: Session SQLAlchemy active.
        athlete_id: ID interne de l'athlète (table athletes, pas strava_id).

    Returns:
        Un stravalib.Client prêt à appeler l'API Strava.

    Raises:
        ValueError: Si l'athlète n'existe pas.
        StravaTokenExpired: Si le refresh échoue (token révoqué par l'utilisateur).
    """
    from db.models import Athlete

    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise ValueError(f"Athlete {athlete_id} not found in database")
    if not athlete.strava_refresh_token:
        raise ValueError(
            f"Athlete {athlete_id} ({athlete.firstname} {athlete.lastname}) "
            "has no Strava refresh token stored."
        )

    client = Client()

    # ── Faut-il refresh ? ──────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    needs_refresh = False

    if athlete.strava_token_expires_at:
        # L'athlète a un expires_at — on vérifie avec le buffer de sécurité
        expires_at = athlete.strava_token_expires_at
        if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
            # Si naive, on suppose UTC
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        threshold = expires_at - REFRESH_BUFFER
        needs_refresh = now >= threshold
    else:
        # Pas d'expires_at stocké → on refresh par précaution
        needs_refresh = True

    # ── Refresh si nécessaire ──────────────────────────────────────────────
    if needs_refresh:
        try:
            token_resp = client.refresh_access_token(
                client_id=STRAVA_CLIENT_ID,
                client_secret=STRAVA_CLIENT_SECRET,
                refresh_token=athlete.strava_refresh_token,
            )
        except Exception as exc:
            raise StravaTokenExpired(
                f"Failed to refresh token for athlete {athlete_id} "
                f"({athlete.firstname} {athlete.lastname}): {exc}"
            )

        new_access = token_resp.get("access_token")
        new_refresh = token_resp.get("refresh_token")
        new_expires_at = token_resp.get("expires_at")

        # Mise à jour en DB
        athlete.strava_refresh_token = new_refresh or athlete.strava_refresh_token
        if new_expires_at:
            athlete.strava_token_expires_at = datetime.fromtimestamp(
                int(new_expires_at), tz=timezone.utc
            )
        db.commit()

        client.access_token = new_access
        print(
            f"🔄 Token refreshé pour athlete {athlete_id} "
            f"({athlete.firstname} {athlete.lastname})"
        )
    else:
        # Token encore valide — on l'utilise directement
        # On a besoin de l'access_token courant. Problème : on ne le stocke pas
        # en DB (seulement le refresh_token). Il faut donc faire un refresh
        # pour obtenir un access_token valide.
        #
        # Solution : on refresh quand même, car Strava permet de refresh
        # un token même s'il n'est pas encore expiré. Le nouvel access_token
        # est immédiatement valide.
        try:
            token_resp = client.refresh_access_token(
                client_id=STRAVA_CLIENT_ID,
                client_secret=STRAVA_CLIENT_SECRET,
                refresh_token=athlete.strava_refresh_token,
            )
        except Exception as exc:
            raise StravaTokenExpired(
                f"Failed to refresh token for athlete {athlete_id}: {exc}"
            )

        new_access = token_resp.get("access_token")
        new_refresh = token_resp.get("refresh_token")
        new_expires_at = token_resp.get("expires_at")

        athlete.strava_refresh_token = new_refresh or athlete.strava_refresh_token
        if new_expires_at:
            athlete.strava_token_expires_at = datetime.fromtimestamp(
                int(new_expires_at), tz=timezone.utc
            )
        db.commit()

        client.access_token = new_access

    return client


def get_strava_client_by_strava_id(
    db: Session, strava_id: int
) -> Client:
    """
    Variante : récupère un client Strava par strava_id (ID Strava, pas ID interne).

    Utile quand on ne connaît que l'ID Strava de l'athlète (ex: lors d'un webhook).
    """
    from db.models import Athlete

    athlete = db.query(Athlete).filter(Athlete.strava_id == strava_id).first()
    if not athlete:
        raise ValueError(f"No athlete found with Strava ID {strava_id}")
    return get_strava_client(db, athlete.id)
