# Coach — compte utilisateur, Strava et résumés physiologiques compacts

Application FastAPI autonome située dans `coach_prototype/`; elle utilise exclusivement PostgreSQL `coach_proto`, jamais les tables de l'ancienne app. Le login est par compte Coach réel (`/signup`, ouvert uniquement au bootstrap `ALLOW_SIGNUP=1`). Après le premier compte, remettre `ALLOW_SIGNUP=0` puis redémarrer. La conversation reste simulée et aucune inférence n'est appelée.

## Pipeline d'activité Strava

- Après le consentement OAuth, l'interface déclenche un import initial des **20 dernières activités**. Un clic ultérieur « Actualiser » récupère les activités postérieures au curseur `last_activity_sync_at` (pagination incrémentale bornée à 500 par passage).
- Les activités et calculs appartiennent à l'utilisateur Coach de la session. Le token d'accès est renouvelé côté serveur ; le refresh token rotatif reste chiffré dans `coach_strava_connections`.
- Chaque activité reçoit une demande de streams en **une seule fois**, à résolution `high`. Le même objet est transmis à `time_report`, `compact_from_streams` et à l'échantillonnage des `streams_json` (300 points au plus).
- `compact_json` conserve le résumé court d'une activité ; `best_json` n'est généré/sauvegardé **que si `device_watts` est vrai**. La roue libre `watts=0` reste du temps actif.
- `/api/activities/{id}/compact` renvoie le JSON minifié avec le nombre de caractères dans l'en-tête `X-Compact-Characters`. `?segment=longest` recadre seulement le résumé course ; le résumé stocké et les courbes restent ceux de toute la séance.
- `time_report` est journalisé pour chaque stream. Si aucune pause `>=3s` n'est trouvée alors que `elapsed_time_s-moving_time_s >120`, un WARNING signale que le stream `time` peut avoir compressé les arrêts ; le moteur ne devine pas de pause.
- `/api/level` ne fait aucun appel Strava : snapshot sur 180 jours, calcul courant 90 j vs les 90 j précédents, cache par utilisateur invalide après synchronisation/recalcul.

Sources compactes : `services/fit_compact.py` (algorithmes temps actif, fenêtres avec `tt`, résumé) et `services/strava_compact.py` (adaptateur de streams). FIT parsing optionnel omis dans la web app.

## Modèle de données vérifié

Dans ce Coach (et pas l'ancien `db/models.py`), le propriétaire est `User.id`; poids/FTP/FC max sont `User.weight_kg`, `User.ftp_watts`, `User.max_heartrate`. Les champs `coach_activities` comprennent `source_id` (Strava), `occurred_at`, `moving_time_s`, `elapsed_time_s`, `device_watts`, `streams_json`, `compact_json`, `best_json`. Le lien Strava OAuth est par `StravaConnection.user_id` vers le `User.id` authentifié. Le callback OAuth renseigne le poids, FTP ou FCmax depuis le profil Strava seulement si la valeur Coach n'a pas déjà été saisie.

## Migration PostgreSQL existante

`Base.metadata.create_all()` ne modifie pas les colonnes d'une table déjà présente. Sur la base isolée `coach_proto`, effectuer la sauvegarde et la migration **avant** de redémarrer l'application mise à jour :

```bash
pg_dump coach_proto > ~/coach_proto_before_compact.sql
psql -d coach_proto -v ON_ERROR_STOP=1 -f /home/nicee/coach/migrations/0002_compact_activity_cache.sql
```

La migration ajoute les champs compacts, device power, durée exacte, HRmax et table cache ; elle élargit `source_id` à BIGINT. Elle ne cible jamais `db_multi_stravbike`.

## Installation des dépendances et tests

```bash
cd /home/nicee/coach
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Les tests temps synthétiques reproduisent le FIT de référence : 1406 records, elapsed 1812s, actif 1417s, pauses 395s, 11 écarts de 2s et segments continus 318/1061s (course crop attendue `[751,1061]`). Les tests n'appellent pas Strava en direct.

## Afficher un résumé réel

Après migration, mise à jour des deux services et synchronisation, ouvrir une activité du tableau puis « Voir le JSON compact ». Pour une course, choisir le résumé de segment le plus long. L'API donne le nombre de caractères via `X-Compact-Characters`. Une valeur d'exemple réelle ne peut être rapportée qu'après cette exécution sur la base de l'utilisateur connecté ; ne partagez jamais le `.env`, un code OAuth ou un refresh token.

Services : app UI `127.0.0.1:2025`, OAuth `127.0.0.1:2024`; Nginx `/auth/` doit proxifier vers 2024, tout le reste vers 2025. Aucun déploiement ou changement de serveur n'est fait par cette branche Git.
