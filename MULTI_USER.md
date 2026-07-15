# Multi-User — Guide de déploiement et d'usage

Ce dossier/document décrit le workflow multi-utilisateur de stravbike.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. OAuth (port 2025)                                               │
│     https://strava-coach.duckdns.org/auth/connect                   │
│     → Strava consent screen                                         │
│     → Formulaire email                                              │
│     → JSON token dans ~/stravbike/data/tokens/<strava_id>.json      │
│                                                                     │
│  2. Ingestion tokens → DB                                           │
│     python -m ingestion.ingest_users_and_athletes                   │
│     → tables users + athletes (strava_refresh_token stocké)         │
│                                                                     │
│  3. Import activités (à la demande)                                 │
│     python -m ingestion.ingest_activities_multi --athlete-id 3      │
│     → table activities (lié à athletes.id)                          │
│                                                                     │
│  4. Sync profil (FTP, poids, zones)                                 │
│     python -m ingestion.ingest_athlete_profiles_multi --all         │
│     → mise à jour des constantes d'entraînement                     │
│                                                                     │
│  5. API multi-athlète                                               │
│     uvicorn api_multi:app --port 8001                               │
│     → routes /api/athletes, /api/activities, etc.                   │
│     → auth par X-API-Key (STRAVBIKE_SERVICE_KEY)                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Prérequis

- Base `db_multi_stravbike` créée (`python init_db.py`)
- `.env` avec `DATABASE_URL=postgresql:///db_multi_stravbike`
- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` dans le `.env`
- `STRAVBIKE_SERVICE_KEY` dans le `.env`

## Workflow pas à pas

### Étape 1 — Connexion OAuth d'un nouvel athlète

L'athlète visite :
```
https://strava-coach.duckdns.org/auth/connect
```
Il autorise Strava, saisit son email, et un JSON est créé dans `data/tokens/`.

### Étape 2 — Migration des tokens vers la DB

```bash
cd ~/stravbike
source .venv/bin/activate
python -m ingestion.ingest_users_and_athletes
```

Résultat attendu :
```
✅ 5 fichier(s) trouvé(s)
✅ User créé: jean@example.com | ✨ Athlete créé: Jean Dupont (Strava ID: 12345)
✅ User créé: marie@example.com | ✨ Athlete créé: Marie Martin (Strava ID: 67890)
...
```

Les tokens JSON peuvent ensuite être supprimés (les credentials sont en DB).

### Étape 3 — Import des activités

**Pour un athlète spécifique :**
```bash
python -m ingestion.ingest_activities_multi --athlete-id 3 --limit 100
```

**Par email :**
```bash
python -m ingestion.ingest_activities_multi --athlete-email jean@example.com --limit 100
```

**Tous les athlètes :**
```bash
python -m ingestion.ingest_activities_multi --all --limit 100
```

**Mode incrémental** (seulement les nouvelles activités depuis le dernier import) :
```bash
python -m ingestion.ingest_activities_multi --all --incremental
```

### Étape 4 — Synchronisation des profils

```bash
# Un athlète
python -m ingestion.ingest_athlete_profiles_multi --athlete-id 3

# Tous
python -m ingestion.ingest_athlete_profiles_multi --all
```

Récupère : FTP, poids, zones de puissance, zones de FC, stats YTD.

## Accès manuel (beta testeurs)

Pour donner accès à un testeur sans passer par l'OAuth complet :

1. Créer l'utilisateur en DB manuellement :
```sql
INSERT INTO users (email, firstname, lastname, password_hash)
VALUES ('test@example.com', 'Jean', 'Dupont', NULL);
```

2. Créer l'athlète avec son refresh token Strava (récupéré via OAuth) :
```sql
INSERT INTO athletes (strava_id, firstname, lastname, owner_user_id, strava_refresh_token)
VALUES (12345678, 'Jean', 'Dupont', 1, 'refresh_token_ici');
```

3. Importer ses activités :
```bash
python -m ingestion.ingest_activities_multi --athlete-id 1
```

## Services systemd (à créer sur le serveur)

### API multi-athlète (port 8001)
```ini
# /etc/systemd/system/stravbike-multi.service
[Unit]
Description=stravbike Multi-Athlete API
After=network.target

[Service]
Type=simple
User=nicee
WorkingDirectory=/home/nicee/stravbike
ExecStart=/home/nicee/stravbike/.venv/bin/uvicorn api_multi:app --host 0.0.0.0 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

### Cron d'import incrémental (toutes les heures)
```cron
0 * * * * cd /home/nicee/stravbike && .venv/bin/python -m ingestion.ingest_activities_multi --all --incremental >> /var/log/stravbike-multi.log 2>&1
```

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `services/strava_client.py` | Fabrique de clients Strava avec refresh auto des tokens |
| `ingestion/ingest_users_and_athletes.py` | Migration JSON → DB (users + athletes) |
| `ingestion/ingest_activities_multi.py` | Import activités par athlète |
| `ingestion/ingest_athlete_profiles_multi.py` | Sync profil (FTP, poids, zones, YTD) |
| `api_multi.py` | API REST multi-athlète |
| `db/models.py` | Schéma SQLAlchemy multi-user |
| `db/database.py` | Connexion DB + init des tables |

## Limitations connues

- Pas d'authentification frontend (magic link / SMTP) — prévu plus tard
- Les tokens ne sont pas chiffrés en DB (à faire en prod)
- Pas de webhook Strava pour les mises à jour automatiques (polling manuel/cron)
- L'ancien `ingest_activities.py` (mono) coexiste — ne pas le confondre avec `ingest_activities_multi.py`
