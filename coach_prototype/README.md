# Coach — application autonome de démonstration

Ceci est une **nouvelle application FastAPI**, entièrement située dans `coach_prototype/` ; elle ne charge ni `app_multi.py` ni les anciens schémas `stravbike`. La conversation, l'authentification de démonstration et le tableau chronologique fonctionnent sur la nouvelle base `coach_proto`. **Aucune requête Strava, OpenWebUI, OpenRouter ou paiement n'est effectuée.**

## Ce que valide la démo

- Connexion du compte `fake_user@test.local` avec mot de passe provenant de `DEMO_PASSWORD` (dans `.env`, jamais dans Git). Le mot de passe choisi pour la démo est `1234` : **ne pas utiliser avec des données réelles**.
- Chat en accueil, messages jetés à chaque rechargement. La réponse et les blocs « réflexion / outil » sont explicitement **simulés**.
- Avatar ouvrant les paramètres par un tiroir animé ; profil, jauge 0–2M par graduations 100k, sélecteur de moteur visuel, langue FR/EN pour le tableau.
- Base séparée avec profil, deux activités et deux documents Markdown fictifs. Tableau triable/filtrable, détail et téléchargement du Markdown. L'API filtre chaque requête par l'utilisateur authentifié.
- Un seul processus sur `127.0.0.1:2025`. Le port 2024 reste **libre pour le futur OAuth**. Le callback `/auth/callback` n'est pas encore implémenté.

## Prérequis / garde-fous

La base PostgreSQL `coach_proto` doit être créée séparément, appartenir à un rôle qui peut s'y connecter et être vide au départ. Le prototype refuse de démarrer si `DATABASE_URL` cible une autre base (sauf `TESTING=1` pour tests isolés SQLite). Il crée ses trois tables `coach_*` et injecte des données fictives uniquement avec `DEMO_MODE=1`. Il **ne lit ni ne modifie** `db_multi_stravbike`.

L'application est publique si Nginx l'expose : `1234` est un mot de passe connu et faible. N'y placez aucun token ni donnée réelle. Ajouter des limites de requêtes côté proxy si ouvert sur Internet. Avant la vraie auth, remplacer complètement le compte et le flux démo, changer le secret de session et isoler les données réelles.

## Installation (à effectuer seulement après revue et accord)

Le code de cette PR doit être déployé en copiant **le contenu de `coach_prototype/` seulement** vers `/home/nicee/coach`, pas toute la branche Git (qui contient aussi l'ancien projet). Sauvegarder puis vider uniquement `/home/nicee/coach` lorsque la PR est validée. Aucune commande destructive n'est exécutée par cette PR.

1. Préparer la base `coach_proto` et l'accès PostgreSQL pour `nicee`. À confirmer avant d'utiliser `createdb`/`sudo`.
2. Installer les dépendances dans un nouveau `.venv` : `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. Copier `.env.example` vers `.env`, fixer `DATABASE_URL=postgresql:///coach_proto`, `DEMO_MODE=1`, `DEMO_PASSWORD=1234` et un `SESSION_SECRET` aléatoire d'au moins 32 caractères. Garder `.env` en mode `600` ; **pas de secrets Strava dans cette démo**.
4. Tester à part : `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v` (utilise SQLite sous `TESTING=1`).
5. Configurer le service systemd depuis `coach-prototype.service` (requiert `sudo` de l'utilisateur), puis basculer Nginx vers `127.0.0.1:2025` après contrôle local de `/health` et `/login`. Ne pas lancer deux services sur 2025 simultanément.

Le code n'a pas été exécuté via les outils GitHub ; les tests doivent être lancés avant mise en ligne. La prochaine phase branchera Strava OAuth sur 2024, les modèles, une vraie piste de consommation des tokens et la persistance des préférences.
