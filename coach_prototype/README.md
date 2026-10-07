# Coach — compte utilisateur réel et première connexion Strava

Application FastAPI autonome située dans `coach_prototype/`. Elle n'importe ni `app_multi.py` ni l'ancien schéma Stravbike. Elle refuse toute base différente de PostgreSQL `coach_proto` (tests SQLite explicitement isolés avec `TESTING=1`). Aucun compte `fake_user@test.local`, mot de passe bootstrap ou donnée fake n'est créé au démarrage.

Le chat reste une simulation visuelle. Cette branche ajoute l'inscription Coach et l'OAuth Strava par compte, mais ne synchronise pas encore les activités Strava dans la timeline.

## Création du premier compte Coach

L'inscription est fermée par défaut. Pour le bootstrap administré du premier compte réel, dans `/home/nicee/coach/.env`, activer temporairement `ALLOW_SIGNUP=1`, puis redémarrer le service 2025. L'utilisateur choisit son email, nom et mot de passe (12 à 128 caractères). L'email est normalisé et vérifié syntaxiquement, mais **pas confirmé par email** dans cette première version. Le mot de passe est haché PBKDF2-HMAC-SHA256 avec sel par compte ; il n'est jamais stocké en clair. Les formulaires d'inscription ont un nonce CSRF et les tentatives sont limitées par adresse IP en mémoire.

Après que le premier compte a été créé, remettre `ALLOW_SIGNUP=0` dans `.env` et redémarrer `coach-prototype`. Le lien signup est alors masqué et les routes d'inscription renvoient 403. Une panne/redémarrage conserve les comptes PostgreSQL.

## Connexion Strava

- L'utilisateur se connecte au compte Coach, puis clique **Connecter Strava** dans Paramètres.
- Service OAuth dédié `oauth_app.py` sur `127.0.0.1:2024`; app web sur `127.0.0.1:2025`.
- `state` cryptographique, à usage unique, expirant en 10 minutes et lié au compte Coach authentifié ; callback refuse session absente/inadéquate, état invalide ou scopes refusés.
- Le champ Callback Domain de la console Strava reçoit seulement `proto.fu19.org`; le redirect OAuth est `https://proto.fu19.org/auth/callback`.
- Scopes demandés : `read,activity:read_all,profile:read_all`.
- Le callback échange le code serveur-à-serveur et lie l'identité athlete Strava à l'ID du compte Coach courant. Un athlète Strava ne peut pas être lié à deux utilisateurs Coach.
- Seul le refresh token est gardé, chiffré en Fernet, avec scopes et expiration. Le token Strava tourne au refresh : `/auth/strava/refresh` stocke toujours la dernière valeur et ne révèle aucun token au navigateur. La clé Fernet perdue impose une nouvelle autorisation.
- Les activités ne sont pas encore importées dans la timeline. Le profil/les lignes fictives de preview ne doivent pas être confondus avec des données Strava réelles.

## `.env` privé

Copier `.env.example` en `.env`, remplir les credentials hors Git et garder permissions 600. Ne jamais transmettre/committer client secret, clés Fernet, codes OAuth ni tokens.

```dotenv
DATABASE_URL=postgresql+psycopg2:///coach_proto
DEMO_MODE=1
ALLOW_SIGNUP=1 # bootstrap premier compte seulement; puis 0
SESSION_SECRET=<secret aléatoire >= 32 caractères>
STRAVA_CLIENT_ID=<client id>
STRAVA_CLIENT_SECRET=<nouveau secret client>
STRAVA_REDIRECT_URI=https://proto.fu19.org/auth/callback
STRAVA_TOKEN_FERNET_KEY=<clé Fernet dédiée et sauvegardée de façon sûre>
```

Générer des secrets localement, ne pas les coller dans le chat :

```bash
/home/nicee/coach/.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))'
/home/nicee/coach/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
chmod 600 /home/nicee/coach/.env
```

Le process OAuth lit le même `.env` depuis son working directory. La valeur Fernet doit être identique pour toute la durée de vie des tokens chiffrés.

## Tests isolés

Depuis `/home/nicee/coach` après installation des nouvelles dépendances :

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Les tests utilisent SQLite temporaire, comptes créés par fixtures, et `httpx.Mock` pour les échanges OAuth ; aucun vrai appel à Strava n'est fait.

## Déploiement systemd

Après merge et copie du contenu de `coach_prototype/` seulement vers `/home/nicee/coach`, (re)charger le process UI pour qu'il crée les nouvelles tables `coach_*`. Ensuite, installer le service OAuth dédié :

```bash
sudo cp /home/nicee/coach/coach-oauth.service /etc/systemd/system/coach-oauth.service
sudo systemctl daemon-reload
sudo systemctl enable --now coach-oauth
```

Service principal existant : `coach-prototype.service`, localhost:2025. OAuth : `coach-oauth.service`, localhost:2024. Nginx doit proxyfier `/auth/` vers 2024 (proxy_pass sans slash final pour conserver `/auth/callback`) et `/` vers 2025. Vérifier `nginx -t`, les deux services et `/health` avant autorisation Strava.

## Sécurité / limites actuelles

- Remplacer le mot de passe de démo connu avant lier un athlete réel ; la première connexion Strava se lie à l'utilisateur Coach connecté, jamais à un singleton global.
- L'inscription n'a pas encore de vérification email/anti-bot durable (limiteur actuel mémoire par worker). Garder `ALLOW_SIGNUP=0` après le bootstrap.
- Le chat est simulé, aucune inférence, synchronisation d'activités, facturation ou consommation de token réelle.
- Aucun serveur ni secret n'est modifié par le code Git. Tests locaux doivent réussir avant le déploiement et avant l'autorisation du compte Strava réel.
