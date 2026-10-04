# Prévisualisation Coach — première PR

Cette PR reconstitue dans les chemins réellement servis par FastAPI l'orientation conversationnelle validée le 28 septembre 2026. Le prototype V2 local (`/home/nicee/stravbike/app/frontend/conversational/templates/conversational_ui_v2.html`, `styles_v2.css`, `app_v2.js`) n'avait **pas été commité** sur `feature/conversational-ui` ; il ne peut donc pas être récupéré par `git pull`. Le présent écran en reprend les choix validés : petit bandeau, chat à l'accueil, paramètres en tiroir via avatar, profil et langue, emplacements crédits/modèle et tableau technique filtrable/triable avec détail modal. La présentation pourra être comparée à ces trois fichiers locaux avant validation graphique finale.

## Ce qui marche dans cette PR

- `/` et la connexion aboutissent à `/chat`, qui sert `frontend/templates/coach.html` via `app_multi.py` (FastAPI, pas Flask).
- Le tiroir et le tableau sont interactifs. Les activités et leurs détails proviennent des routes existantes protégées par cookie (`/api/activities/` et `/api/activities/{id}`), déjà filtrées par athlète côté serveur.
- Les contenus de l'API sont ajoutés au DOM avec `textContent`, pas interpolés en HTML.
- Le chat est réinitialisé à chaque chargement. Le compositeur reste désactivé **exprès** : aucun appel à l'ancien modèle OpenWebUI n'est fait par cette page.
- Le code conserve des styles dédiés aux blocs de réflexion (`details`) et d'état des outils pour leur future intégration au streaming ; la logique SSE existante de `frontend/static/js/chat.js` est à reprendre et à tester lors de l'orchestration.
- Les nouveaux fichiers statiques passent sous `/static/` comme les autres ressources de l'application.

## Non livré / blocages avant déploiement public

- La base ne contient pas encore les artefacts Markdown ni de registre de crédits et de consommation. La jauge est marquée *non disponible*, pas remplie avec de fausses valeurs ; le choix du modèle est désactivé. Pas de facturation, de Stripe ou de débit de tokens dans cette PR.
- Le choix de langue ne change que l'affichage technique du tableau et des détails ; aucune valeur n'est enregistrée en base ni envoyée au futur LM handler.
- L'avatar affiche la photo de profil existante si présente ; téléversement/modification et stockage en base restent à concevoir.
- Les anciennes routes calendrier/activités/profil du dépôt `master` subsistent côté backend pour compatibilité. La nouvelle interface ne leur donne plus de navigation.
- **Sécurité bloquante :** le login actuel de `app_multi.py` authentifie par email seul. Ne pas mettre cette version à disposition du public avant une véritable vérification du mot de passe ou magic link. Vérifier également les cookies et limiter l'accès aux endpoints historiques.
- Révoquer et renouveler les secrets exposés pendant les essais antérieurs ; ne jamais les committer.

## Revue et essais

Dans un environnement isolé (pas la base de production), depuis la racine du dépôt : `python -m unittest discover -s tests -p 'test_coach_preview.py'`. Ce test ne valide pas l'authentification réelle, la DB, l'inférence ni l'affichage sur Gboard : procéder à ces vérifications avant déploiement. Aucun test ni déploiement serveur n'a été exécuté par les outils GitHub de cette PR.
