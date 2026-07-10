# auth/ — Micro-app OAuth Strava

Flow **OAuth Authorization Code** pour la connexion multi-utilisateurs.

Micro-app FastAPI indépendante (port 2025) qui gère l'authentification Strava
sans toucher à l'app principale.

## Routes

| Route              | Méthode | Description |
|--------------------|---------|-------------|
| `/auth/connect`    | GET     | Redirige vers la page d'autorisation Strava |
| `/auth/callback`   | GET     | Reçoit le code, échange les tokens, stocke un JSON |

## Démarrage

```bash
uvicorn auth.main:app --host 0.0.0.0 --port 2025
```

## Variables d'environnement

Voir `.env.example`. Les valeurs réelles sont sur le serveur (non versionnées).

| Variable              | Description                          | Exemple |
|-----------------------|--------------------------------------|---------|
| `STRAVA_CLIENT_ID`    | ID de l'app Strava                   | `12345` |
| `STRAVA_CLIENT_SECRET`| Secret de l'app Strava               | `abc...` |
| `OAUTH_REDIRECT_URI`  | URL de callback HTTPS (via Nginx)    | `https://strava-coach.duckdns.org/auth/callback` |
| `TOKENS_DIR`          | Répertoire de stockage des tokens    | `/data/tokens` |

## Sortie

Chaque connexion crée un fichier `<athlete_id>.json` dans `TOKENS_DIR` :

```json
{
  "athlete_id": 12345678,
  "firstname": "Jean",
  "lastname": "Dupont",
  "profile_pic_url": "https://...",
  "access_token": "xyz...",
  "refresh_token": "abc...",
  "expires_at": 1715000000,
  "scope": "activity:read_all,profile:read_all",
  "created_at": "2025-01-15T12:00:00+00:00"
}
```

## Prérequis côté Strava

Vérifier dans [settings.strava.com](https://www.strava.com/settings/api) :

1. **Callback Domain** doit contenir `strava-coach.duckdns.org`
   (domaine seul, sans protocole ni chemin)
2. Le `client_id` / `client_secret` sont les mêmes que l'app existante

## Nginx

Le reverse proxy doit rediriger le préfixe `/auth/` vers le port 2025 :

```nginx
location /auth/ {
    proxy_pass http://localhost:2025;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Flow complet

```
1. Utilisateur → https://strava-coach.duckdns.org/auth/connect
2. Nginx → localhost:2025/auth/connect
3. App → redirect 302 vers strava.com/oauth/authorize
4. Strava affiche le consent screen
5. Utilisateur clique "Authorize"
6. Strava → redirect vers /auth/callback?code=XXXX
7. Nginx → localhost:2025/auth/callback?code=XXXX
8. App échange le code → tokens Strava
9. App récupère le profil athlète
10. App écrit /data/tokens/<id>.json
11. App affiche la page de succès
```
