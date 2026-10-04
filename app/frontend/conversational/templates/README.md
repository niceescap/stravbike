# Template du Chatbot Stravbike

Ce répertoire contient le template original du chatbot Stravbike extrait de la branche master, qui servira de base pour l'interface conversationnelle.

## Fichiers inclus

1. **chat_template.html** - Template HTML principal du chatbot
2. **chat_styles.css** - Feuille de style CSS pour le design du chat
3. **chat_app.js** - JavaScript gérant l'interaction et la logique du chat
4. **chat_config.json** - Configuration du chatbot (modèles, paramètres, etc.)

## Design original

Le template utilise le design système existant de Stravbike avec :
- Thème sombre
- Couleurs principales : orange (#FF6B35) pour l'utilisateur, menthe (#00D4AA) pour l'assistant
- Interface responsive adaptée aux mobiles
- Support du streaming SSE pour les réponses en temps réel
- Affichage des étapes de raisonnement et statut des outils

## Intégration

Ces fichiers seront intégrés dans l'application FastAPI existante et connectés aux endpoints backend pour :
- L'authentification via la clé API
- L'appel aux modèles LLM via le proxy /api/chat/
- La gestion de l'historique des conversations
- Le suivi de la consommation de tokens

## Structure du template

```
chat_template.html
├── {% extends "base.html" %}
├── #chat-container (conteneur principal)
│   ├── #chat-model-badge (badge du modèle actif)
│   ├── #chat-messages (zone d'affichage des messages)
│   │   ├── .chat-welcome (message d'accueil)
│   │   └── .chat-message (messages utilisateur/assistant)
│   └── #chat-input-wrap (zone de saisie)
│       ├── #chat-input (textarea)
│       └── #chat-send (bouton d'envoi)
└── {% block scripts %}
    └── <script src="/static/js/chat.js"></script>
```