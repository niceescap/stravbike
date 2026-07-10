"""
auth/main.py — Micro-app FastAPI : OAuth Authorization Code Flow (Strava)

Démarrage :
    uvicorn auth.main:app --host 0.0.0.0 --port 2025

Routes :
    GET /auth/connect   → redirection vers Strava (page d'autorisation)
    GET /auth/callback  → réception du code, échange de tokens, stockage JSON

Stockage :
    /data/tokens/<athlete_id>.json
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

load_dotenv()

# ── Configuration (lue depuis .env — valeurs réelles sur le serveur) ──────
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv(
    "OAUTH_REDIRECT_URI",
    "https://strava-coach.duckdns.org/auth/callback",
)
TOKENS_DIR = Path(os.getenv("TOKENS_DIR", "/data/tokens"))

# ── Constantes Strava ─────────────────────────────────────────────────────
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ATHLETE_URL = "https://www.strava.com/api/v3/athlete"
STRAVA_SCOPE = "activity:read_all,profile:read_all"

app = FastAPI(title="stravbike-auth", docs_url=None, redoc_url=None)


# ── Route 1 : /auth/connect ───────────────────────────────────────────────
@app.get("/auth/connect")
async def auth_connect():
    """Redirige l'utilisateur vers la page d'autorisation Strava."""
    params = urlencode({
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": STRAVA_SCOPE,
    })
    return RedirectResponse(f"{STRAVA_AUTH_URL}?{params}", status_code=302)


# ── Route 2 : /auth/callback ──────────────────────────────────────────────
@app.get("/auth/callback")
async def auth_callback(
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    scope: str | None = None,
):
    """
    Reçoit le callback Strava après autorisation.
    Échange le code contre les tokens, récupère le profil athlète, et
    stocke le tout dans /data/tokens/<athlete_id>.json.
    """
    # Cas 1 : l'utilisateur a refusé l'autorisation
    if error:
        msg = f"Autorisation refusée : {error}"
        if error_description:
            msg += f" — {error_description}"
        return HTMLResponse(content=_error_page(msg), status_code=400)

    # Cas 2 : pas de code reçu (appel direct sans paramètres Strava)
    if not code:
        return HTMLResponse(
            content=_error_page("Aucun code d'autorisation reçu."),
            status_code=400,
        )

    # Étape 1 : échange du code contre les tokens
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": STRAVA_CLIENT_ID,
                    "client_secret": STRAVA_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            resp.raise_for_status()
            token_data = resp.json()
        except httpx.HTTPStatusError:
            return HTMLResponse(
                content=_error_page(
                    f"Échange de tokens échoué (HTTP {resp.status_code}) : "
                    f"{resp.text}"
                ),
                status_code=502,
            )
        except httpx.RequestError as exc:
            return HTMLResponse(
                content=_error_page(f"Erreur réseau lors de l'échange : {exc}"),
                status_code=502,
            )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_at = token_data.get("expires_at")

    if not access_token or not refresh_token:
        return HTMLResponse(
            content=_error_page(f"Réponse Strava incomplète : {token_data}"),
            status_code=502,
        )

    # Étape 2 : récupération du profil athlète
    # (Strava ne renvoie plus l'objet athlete dans /oauth/token depuis 2023)
    athlete_data = {}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                STRAVA_ATHLETE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            resp.raise_for_status()
            athlete_data = resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError):
            # Tokens valides mais profil inaccessible — on stocke quand même.
            pass

    athlete_id = athlete_data.get("id") or token_data.get("athlete", {}).get("id")
    if not athlete_id:
        return HTMLResponse(
            content=_error_page("Impossible de récupérer l'ID athlète."),
            status_code=502,
        )

    # Étape 3 : construction de l'enregistrement et stockage fichier
    record = {
        "athlete_id": athlete_id,
        "firstname": athlete_data.get("firstname", ""),
        "lastname": athlete_data.get("lastname", ""),
        "profile_pic_url": athlete_data.get("profile_medium", ""),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": scope or STRAVA_SCOPE,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    token_file = TOKENS_DIR / f"{athlete_id}.json"
    token_file.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return HTMLResponse(content=_success_page(athlete_data, token_file))


# ── Pages HTML ────────────────────────────────────────────────────────────

def _success_page(athlete: dict, token_file: Path) -> str:
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    athlete_id = athlete.get("id", "?")
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Connexion réussie — stravbike</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 500px;
           margin: 80px auto; text-align: center; color: #333; }}
    .card {{ background: #f8f9fa; border-radius: 12px; padding: 32px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    .detail {{ color: #6c757d; font-size: 14px; margin-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Connexion réussie !</h1>
    <p>Bienvenue <strong>{name}</strong> (ID Strava : {athlete_id})</p>
    <p class="detail">Tokens stockés dans : <code>{token_file}</code></p>
  </div>
</body>
</html>"""


def _error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Erreur — stravbike</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 500px;
           margin: 80px auto; text-align: center; color: #333; }}
    .card {{ background: #fff5f5; border: 1px solid #ffb4b4;
            border-radius: 12px; padding: 32px; }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    .detail {{ color: #6c757d; font-size: 14px; margin-top: 16px;
              word-break: break-word; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">❌</div>
    <h1>Connexion échouée</h1>
    <p class="detail">{message}</p>
  </div>
</body>
</html>"""
