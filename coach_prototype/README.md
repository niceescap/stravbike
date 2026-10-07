# Coach — compte utilisateur et première connexion Strava

Application FastAPI autonome sous `coach_prototype/`. Elle n'importe ni `app_multi.py` ni les anciennes tables Stravbike. Elle refuse toute base autre que PostgreSQL `coach_proto` (tests SQLite uniquement lorsque `TESTING=1`). Le démarrage crée les tables Coach, mais **ne crée aucun utilisateur, activité ou artefact fictif**. Aucune référence au compte `fake_user@test.local` n'existe dans cette app.

Le chat reste simulé. Cette branche ajoute l'inscription Coach réelle et l'association OAuth Strava, mais la synchronisation des activités est une étape ultérieure.

## Créer le premier compte Coach

L'inscription est **fermée par défaut**. Pour le bootstrap du premier compte réel, dans `/home/nicee/coach/.env`, activez temporairement `ALLOW_SIGNUP=1`, puis redémarrez `coach-prototype`. Depuis `https://proto.fu19.org/signup`, l'utilisateur choisit son propre email, nom affiché et mot de passe (12–128 caractères). L'email est validé syntaxiquement et normalisé, mais **pas vérifié par email**. Le mot de passe est haché PBKDF2-HMAC-SHA256 avec sel par compte. Le formulaire a un nonce CSRF et un limiteur de tentatives par IP en mémoire.

Dès que le compte initial est créé, remettez `ALLOW_SIGNUP=0` dans `.env` et redémarrez `coach-prototype`. Le lien signup disparaît, et `/signup` est refusé. L'utilisateur conserve l'accès à son compte ; aucune identité de démonstration n'est créée ou requise.

## OAuth Strava

- L'utilisateur s'inscrit/se connecte au compte Coach puis clique **Connecter Strava** dans Paramètres.
- OAuth est un service distinct sur `127.0.0.1:2024`; app web sur `127.0.0.1:2025`.
- `GET /auth/strava` exige le cookie de session signé, stocke un `state` aléatoire, lié à l'ID Coach, expirant en 10 minutes et utilisable une seule fois.
- Callback exact : `https://proto.fu19.org/auth/callback`. Dans la console développeur Strava, le champ Callback Domain contient seulement `proto.fu19.org`.
- Scopes requis : `read,activity:read_all,profile:read_all` ; l'échange échoue si les scopes d'activité/profil ne sont pas retournés.
- Le code est échangé côté serveur. Le `strava_athlete_id` est unique et lié à un seul utilisateur Coach.
- Seul le refresh token est conservé, chiffré par Fernet dans `coach_strava_connections`. Le token d'accès éphémère n'est ni persisté ni rendu au navigateur. `/auth/strava/refresh` sauvegarde toujours le refresh token rotatif et n'en divulgue pas la valeur.
- Après connexion, le tiroir affiche le profil Strava. **Les activités ne sont pas encore importées** et la conversation reste simulée.

## `.env` privé

Ne jamais committer `.env`, transmettre des secrets dans une conversation ou afficher le fichier complet. Garde `chmod 600`. Valeurs attendues :

```dotenv
DATABASE_URL=postgresql+psycopg2:///coach_proto
DEMO_MODE=1
ALLOW_SIGNUP=0
SESSION_SECRET=<secret aléatoire >= 32 caractères>
STRAVA_CLIENT_ID=<client id>
STRAVA_CLIENT_SECRET=<nouveau client secret>
STRAVA_REDIRECT_URI=https://proto.fu19.org/auth/callback
STRAVA_TOKEN_FERNET_KEY=<clé Fernet privée et sauvegardée>
```

Générer localement (ne pas copier les valeurs dans le chat) :

```bash
/home/nicee/coach/.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))'
/home/nicee/coach/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
chmod 600 /home/nicee/coach/.env
```

Conserver la clé Fernet en sauvegarde sûre : sa perte rend les refresh tokens existants indéchiffrables.

## Tests isolés

```bash
cd /home/nicee/coach
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Tests en SQLite temporaire ; les requêtes Strava du test sont mockées. Ils ne prouvent pas le callback réel ni la connectivité réseau/API Strava.

## Déploiement systemd (après revue/merge)

Copier uniquement le contenu de `coach_prototype/` vers `/home/nicee/coach`, jamais la racine historique du dépôt. Créer `coach_proto` et accorder les droits au rôle PostgreSQL `nicee`. Après mise à jour du code, redémarrer l'app 2025 pour création des nouvelles tables, puis installer OAuth :

```bash
sudo cp /home/nicee/coach/coach-oauth.service /etc/systemd/system/coach-oauth.service
sudo systemctl daemon-reload
sudo systemctl enable --now coach-oauth
```

Nginx garde `/` vers `127.0.0.1:2025` et `/auth/` vers `127.0.0.1:2024`, avec `proxy_pass http://127.0.0.1:2024;` **sans slash final** pour préserver `/auth/callback`. Les services sont localhost only. Tester Nginx et les deux health checks avant de démarrer le vrai OAuth.

## Limites / sécurité

- L'inscription ouverte est un interrupteur de bootstrap : la fermer (`ALLOW_SIGNUP=0`) après le premier compte.
- Pas de confirmation email ni récupération de mot de passe dans cette première version.
- Le chat reste simulé, sans LLM, facturation ou consommation de token réelle. Aucune activité réelle n'est importée par ce flux OAuth seul.
- Ne pas supprimer automatiquement un compte ou des données existantes ; migration/assainissement éventuel à examiner séparément.
- Aucun service du serveur, `.env`, base ou Nginx n'est modifié par les commits Git.
