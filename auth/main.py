"""
auth/main.py — Micro-app FastAPI : OAuth Authorization Code Flow (Strava)

Démarrage :
    uvicorn auth.main:app --host 0.0.0.0 --port 2025

Routes :
    GET /auth/connect          → redirection vers Strava
    GET /auth/callback         → réception du code, affiche formulaire email
    POST /auth/confirm-email   → validation email, stockage JSON final

Stockage :
    /data/tokens/<athlete_id>.json (avec email inclus)
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import secrets

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

load_dotenv()

# ── Configuration (lue depuis .env) ────────────────────────────────────────
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv(
    "OAUTH_REDIRECT_URI",
    "https://strava-coach.duckdns.org/auth/callback",
)
TOKENS_DIR = Path(os.getenv("TOKENS_DIR", "/home/nicee/stravbike/data/tokens"))

# ── Constantes Strava ─────────────────────────────────────────────────────
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ATHLETE_URL = "https://www.strava.com/api/v3/athlete"
STRAVA_SCOPE = "activity:read_all,profile:read_all"

# ── Store temporaire (en RAM pendant la session) ────────────────────────────
# Format : {temp_token: {athlete_id, access_token, refresh_token, expires_at, athlete_data}}
# Nettoyé après 15 min ou après confirmation
TEMP_AUTH_SESSIONS = {}

app = FastAPI(title="stravbike-auth", docs_url=None, redoc_url=None)


# ============================================================================
# Helpers
# ============================================================================

def _generate_temp_token() -> str:
    """Génère un token temporaire (UUID) pour la session OAuth."""
    return secrets.token_urlsafe(32)


def _cleanup_temp_session(temp_token: str):
    """Supprime une session temporaire."""
    if temp_token in TEMP_AUTH_SESSIONS:
        del TEMP_AUTH_SESSIONS[temp_token]


# ============================================================================
# Route 1 : /auth/connect
# ============================================================================

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


# ============================================================================
# Route 2 : /auth/callback (réception du code Strava)
# ============================================================================

@app.get("/auth/callback")
async def auth_callback(
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    scope: str | None = None,
):
    """
    Reçoit le callback Strava après autorisation.
    
    Étapes :
      1. Échange code → tokens
      2. Récupère profil athlète
      3. Stocke en session temporaire
      4. Affiche formulaire pour confirmer email
    """
    
    # Cas 1 : l'utilisateur a refusé l'autorisation
    if error:
        msg = f"Autorisation refusée : {error}"
        if error_description:
            msg += f" — {error_description}"
        return HTMLResponse(content=_error_page(msg), status_code=400)

    # Cas 2 : pas de code reçu
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
                    f"Échange de tokens échoué (HTTP {resp.status_code})"
                ),
                status_code=502,
            )
        except httpx.RequestError as exc:
            return HTMLResponse(
                content=_error_page(f"Erreur réseau : {exc}"),
                status_code=502,
            )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_at = token_data.get("expires_at")

    if not access_token or not refresh_token:
        return HTMLResponse(
            content=_error_page("Réponse Strava incomplète"),
            status_code=502,
        )

    # Étape 2 : récupération du profil athlète
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
            # Token valide mais profil inaccessible — on continue
            pass

    athlete_id = athlete_data.get("id")
    if not athlete_id:
        return HTMLResponse(
            content=_error_page("Impossible de récupérer l'ID athlète."),
            status_code=502,
        )

    # Étape 3 : stockage en session temporaire + affichage formulaire email
    temp_token = _generate_temp_token()
    TEMP_AUTH_SESSIONS[temp_token] = {
        "athlete_id": athlete_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": scope or STRAVA_SCOPE,
        "athlete_data": athlete_data,
    }

    return HTMLResponse(content=_email_form_page(temp_token, athlete_data))


# ============================================================================
# Route 3 : /auth/confirm-email (soumission du formulaire email)
# ============================================================================

@app.post("/auth/confirm-email")
async def confirm_email(
    temp_token: str = Form(...),
    email: str = Form(...),
):
    """
    Reçoit la confirmation d'email depuis le formulaire.
    
    Finalise le stockage du JSON avec l'email réel.
    """
    
    # Récupère la session temporaire
    if temp_token not in TEMP_AUTH_SESSIONS:
        return HTMLResponse(
            content=_error_page("Session expirée. Recommence la connexion."),
            status_code=400,
        )

    session = TEMP_AUTH_SESSIONS[temp_token]
    
    # Validation basique de l'email
    if not email or "@" not in email:
        return HTMLResponse(
            content=_email_form_page(
                temp_token,
                session["athlete_data"],
                error="Email invalide. Réessaie."
            ),
            status_code=400,
        )

    # Construction de l'enregistrement complet
    record = {
        "athlete_id": session["athlete_id"],
        "firstname": session["athlete_data"].get("firstname", ""),
        "lastname": session["athlete_data"].get("lastname", ""),
        "profile_pic_url": session["athlete_data"].get("profile_medium", ""),
        "email": email,  # ✅ Email saisi par l'utilisateur
        "access_token": session["access_token"],
        "refresh_token": session["refresh_token"],
        "expires_at": session["expires_at"],
        "scope": session["scope"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Stockage du JSON
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    token_file = TOKENS_DIR / f"{session['athlete_id']}.json"
    token_file.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Nettoyage de la session temporaire
    _cleanup_temp_session(temp_token)

    return HTMLResponse(
        content=_success_page(session["athlete_data"], email, token_file)
    )


# ============================================================================
# Pages HTML
# ============================================================================

def _email_form_page(temp_token: str, athlete: dict, error: str = "") -> str:
    """Formulaire pour confirmer/saisir l'email."""
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    athlete_id = athlete.get("id", "?")
    
    error_html = ""
    if error:
        error_html = f'<div class="error-banner">{error}</div>'
    
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Confirmer email — stravbike</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 500px;
      margin: 60px auto;
      padding: 16px;
      color: #333;
      background: #f5f5f5;
    }}
    .card {{
      background: white;
      border-radius: 12px;
      padding: 32px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.1);
    }}
    h1 {{
      margin-top: 0;
      font-size: 24px;
    }}
    .subtitle {{
      color: #666;
      margin-bottom: 24px;
    }}
    .error-banner {{
      background: #fff3cd;
      border: 1px solid #ffc107;
      color: #856404;
      padding: 12px;
      border-radius: 6px;
      margin-bottom: 16px;
      font-size: 14px;
    }}
    form {{
      display: flex;
      flex-direction: column;
    }}
    label {{
      font-weight: 500;
      margin-bottom: 8px;
      margin-top: 16px;
    }}
    label:first-of-type {{
      margin-top: 0;
    }}
    input {{
      padding: 10px 12px;
      border: 1px solid #ddd;
      border-radius: 6px;
      font-size: 14px;
      font-family: system-ui, sans-serif;
    }}
    input:focus {{
      outline: none;
      border-color: #FF6B35;
      box-shadow: 0 0 0 3px rgba(255, 107, 53, 0.1);
    }}
    button {{
      margin-top: 24px;
      padding: 12px 16px;
      background: #FF6B35;
      color: white;
      border: none;
      border-radius: 6px;
      font-size: 16px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }}
    button:hover {{
      background: #e55a24;
    }}
    .hint {{
      font-size: 12px;
      color: #999;
      margin-top: 6px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Dernière étape</h1>
    <p class="subtitle">Confirme ton adresse email pour <strong>{name}</strong></p>
    {error_html}
    <form method="POST" action="/auth/confirm-email">
      <input type="hidden" name="temp_token" value="{temp_token}">
      <label for="email">Adresse email :</label>
      <input 
        type="email" 
        id="email" 
        name="email" 
        required 
        autofocus
        placeholder="toi@example.com"
      >
      <p class="hint">Cette adresse sera utilisée pour ton compte stravbike.</p>
      <button type="submit">Valider et terminer</button>
    </form>
  </div>
</body>
</html>"""


def _success_page(athlete: dict, email: str, token_file: Path) -> str:
    """Page de succès après confirmation email."""
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    athlete_id = athlete.get("id", "?")
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Connexion réussie — stravbike</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 500px;
      margin: 60px auto;
      padding: 16px;
      color: #333;
      background: #f5f5f5;
    }}
    .card {{
      background: white;
      border-radius: 12px;
      padding: 32px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.1);
      text-align: center;
    }}
    .icon {{
      font-size: 56px;
      margin-bottom: 16px;
    }}
    h1 {{
      margin: 0 0 8px 0;
      color: #1a1a1a;
    }}
    .detail {{
      background: #f8f9fa;
      border-radius: 6px;
      padding: 12px;
      margin-top: 16px;
      font-size: 13px;
      color: #666;
      font-family: 'Courier New', monospace;
      word-break: break-all;
    }}
    .email {{
      font-weight: 500;
      color: #FF6B35;
      margin-top: 8px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Connexion réussie !</h1>
    <p>Bienvenue <strong>{name}</strong></p>
    <div class="detail">
      <div>Email : <span class="email">{email}</span></div>
      <div>ID Strava : {athlete_id}</div>
    </div>
    <p style="margin-top: 24px; font-size: 14px; color: #666;">
      Tu peux maintenant fermer cette fenêtre ou revenir à l'app.
    </p>
  </div>
</body>
</html>"""


def _error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Erreur — stravbike</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 500px;
      margin: 60px auto;
      padding: 16px;
      color: #333;
      background: #f5f5f5;
    }}
    .card {{
      background: white;
      border: 1px solid #f5a5a5;
      border-radius: 12px;
      padding: 32px;
      text-align: center;
      box-shadow: 0 2px 12px rgba(0,0,0,0.1);
    }}
    .icon {{
      font-size: 56px;
      margin-bottom: 16px;
    }}
    h1 {{
      margin: 0 0 8px 0;
    }}
    .detail {{
      color: #666;
      font-size: 14px;
      margin-top: 16px;
      word-break: break-word;
    }}
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
