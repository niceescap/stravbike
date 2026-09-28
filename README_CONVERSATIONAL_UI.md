# Feature Branch: Conversational UI

Cette branche contient le développement de la nouvelle interface utilisateur basée sur la conversation avec un coach IA.

## Objectif

Refondre l'expérience utilisateur autour d'une interface conversationnelle minimaliste:
- Suppression des fonctionnalités inutilisées (calendrier, séances planifiées, commentaires)
- Interface à deux onglets uniquement: Chat principal + Paramètres
- Le modèle IA a un accès complet en lecture/écriture à la base de données
- Génération automatique d'artefacts (plans de séance, analyses) au format Markdown

## Structure de la Branche

```
app/
├── conversation/
│   ├── api/          # Endpoints de l'API conversationnelle
│   ├── models/       # Modèles de données et schémas
│   ├── services/     # Services de traitement et intégration IA
│   └── utils/        # Fonctions utilitaires
└── frontend/
    └── conversational/ # Composants d'interface conversationnelle
```

## Principales Innovations

1. **Session isolée**: Chaque conversation est réinitialisée à l'ouverture/refresh
2. **Contexte intelligent**: Le modèle IA reçoit automatiquement le contexte athlète
3. **Artefacts persistants**: Les plans et analyses générés sont sauvegardés
4. **Intégration flexible**: Compatible avec OpenRouter, AlibabaCloud, etc.

## Étapes de Développement

1. ✅ Phase 1: Conception architecturale (EN COURS)
2. 🔜 Phase 2: Implémentation backend/frontend
3. 🔜 Phase 3: Intégration avec les modèles IA
4. 🔜 Phase 4: Tests et raffinement

## Documentation Associée

- [Schéma de Base de Données](app/conversation/models/database_schema.md)
- [Spécification API](app/conversation/api/specification.md)
- [Spécification Interface](app/frontend/conversational/interface_spec.md)