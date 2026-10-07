# Coach — démo isolée et première connexion Strava

Application autonome FastAPI située dans `coach_prototype/`. Elle ne charge ni `app_multi.py` ni les anciens modèles/tables Stravbike. Sa base autorisée est exclusivement PostgreSQL `coach_proto`. La démo du chat reste simulée ; **elle n'appelle aucun LLM**. Les exemples d'activités et Markdown restent fictifs jusqu'à l'étape de synchronisation.

## Démo et connexion locale

- Compte de démonstration `fake_user@test.local`; mot de passe lu depuis `DEMO_PASSWORD`, jamais intégré au code. `1234` n'est acceptable que temporairement, avec données fictives et accès administrateur privé ; remplacer par un secret long avant de lier Strava.
- Profil, crédit et modèles demeurent des données/choix de démo.
- À chaque rechargement, l'historique de chat simulé est réinitialisé.

## OAuth Strava livré par cette branche

Un service FastAPI distinct, `oauth_app.py`, doit écouter exclusivement sur `127.0.0.1:2024`. Le service principal continue sur `127.0.0.1:2025`.

- `GET /auth/strava` exige la session de l'utilisateur local et crée un `state` CSRF aléatoire, à durée courte, à usage unique et lié à son ID.
- Le callback exact est `https://proto.fu19.org/auth/callback`. Dans les réglages de l'application développeur Strava, le champ *Callback domain* doit contenir seulement `proto.fu19.org`.
- Les scopes demandés sont `read,activity:read_all,profile:read_all`; le callback refuse de stocker la connexion si `activity:read_all` ou `profile:read_all` manquent.
- Échange du code côté serveur. L'identifiant Strava est lié à un seul utilisateur local. Seul le refresh token rotatif est stocké, chiffré par Fernet dans `coach_strava_connections`; ni le token d'accès ni le secret client ne sont renvoyés au navigateur ou journalisés.
- `POST /auth/strava/refresh` renouvelle le token du compte connecté et persiste le nouveau refresh token ; aucun token n'est retourné au client. La fonction renvoie vers la page compte.
- `GET /auth/status` renvoie uniquement l'état et les métadonnées non secrètes du compte lié.
- Le bouton compte s'affiche dans le tiroir des paramètres.

**Limite importante :** cette phase connecte Strava et conserve le refresh token chiffré, mais n'importe pas encore les activités réelles dans le tableau. Celui-ci montre encore les exemples fictifs. Le chat reste simulé. Aucune inférence, dépense de token ou facturation n'est activée.

## Variables privées `.env`

Copier `.env.example` en `.env`, remplir les champs sur le serveur, ne jamais committer `.env` :

```dotenv
DATABASE_URL=postgresql:///coach_proto
DEMO_MODE=1
DEMO_PASSWORD=<secret privé temporaire, à remplacer pour l'accès public>
SESSION_SECRET=<secret aléatoire de 64 caractères hexadécimaux>
STRAVA_CLIENT_ID=<client id de l'application>
STRAVA_CLIENT_SECRET=<nouveau client secret>
STRAVA_REDIRECT_URI=https://proto.fu19.org/auth/callback
STRAVA_TOKEN_FERNET_KEY=<clé Fernet générée une fois et sauvegardée en lieu sûr>
```

Générer les secrets, sans les afficher dans les sorties de diagnostic partagées :

```bash
/home/nicee/coach/.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))'
/home/nicee/coach/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
chmod 600 /home/nicee/coach/.env
```

Le Fernet key est indispensable pour lire les refresh tokens déjà chiffrés ; sauvegarder cette clé dans un gestionnaire de secrets. Si elle est perdue, les comptes Strava devront réautoriser l'application.

## Déploiement — seulement après merge/revue

Copier **le contenu de `coach_prototype/`**, pas la racine du dépôt, vers `/home/nicee/coach`. Créer auparavant la base séparée `coach_proto`, détenue par l'utilisateur PostgreSQL `nicee`. Les processus n'écoutent que localhost.

Installer les dépendances et vérifier l'isolation/tests :

```bash
cd /home/nicee/coach
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Installer deux services distincts (actions sudo opérées par l'administrateur) :

```bash
sudo cp /home/nicee/coach/coach-prototype.service /etc/systemd/system/
sudo cp /home/nicee/coach/coach-oauth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coach-prototype coach-oauth
```

Confirmer les deux listeners locaux : app `2025`, OAuth `2024`. Nginx conserve `location /` vers 2025 et ajoute/remplace la route spécifique :

```nginx
location ^~ /auth/ {
    proxy_pass http://127.0.0.1:2024;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Le `proxy_pass` sans URI finale conserve `/auth/callback`. Tester la config Nginx avant son reload. Ne pas autoriser Strava avant que les deux services soient actifs et que `/auth/strava` puis `/auth/callback` passent par HTTPS.

## Tests

Le test OAuth contrôle les scopes/redirect/state sans contacter Strava. Le test ne peut pas valider un vrai échange d'autorisation ; pour cela, utiliser un seul compte pilote après la revue de sécurité et le démarrage du service OAuth. Aucun secret réel ni token n'est requis pour les tests.
