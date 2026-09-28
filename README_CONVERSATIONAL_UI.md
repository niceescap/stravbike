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
        └── components/ # Composants UI individuels
```

## Principales Innovations

1. **Session isolée**: Chaque conversation est réinitialisée à l'ouverture/refresh
2. **Contexte intelligent**: Le modèle IA reçoit automatiquement le contexte athlète
3. **Artefacts persistants**: Les plans et analyses générés sont sauvegardés
4. **Intégration flexible**: Compatible avec OpenRouter, AlibabaCloud, etc.
5. **Gestion des crédits**: Suivi de la consommation de tokens par athlète
6. **Liste unifiée**: Activités Strava et artefacts MD dans une vue chronologique

## Étapes de Développement

1. ✅ Phase 1: Conception architecturale (EN COURS)
2. 🔜 Phase 2: Implémentation backend/frontend
3. 🔜 Phase 3: Intégration avec les modèles IA
4. 🔜 Phase 4: Tests et raffinement

## Documentation Associée

- [Schéma de Base de Données](app/conversation/models/database_schema.md)
- [Spécification API](app/conversation/api/specification.md)
- [Spécification Interface](app/frontend/conversational/interface_spec.md)

## Composants Créés

### Backend
- [Gestion des crédits et tokens](app/conversation/models/user_credits.py)
- [Modèles d'artefacts](app/conversation/models/artifacts.py)
- [Suivi de consommation](app/conversation/services/token_tracker.py)

### Frontend
- [Liste unifiée d'activités](app/frontend/conversational/components/activity_list.py)
- [Widget de crédits et sélection de modèle](app/frontend/conversational/components/credit_widget.py)

## Fonctionnalités Futures

### Gestion des Crédits
- Jauge de consommation en temps réel
- Sélection de modèles avec coûts différenciés
- Script d'administration pour ajouter des crédits
- Suivi détaillé par athlète

### Artefacts et Activités
- Vue unifiée chronologique
- Différenciation visuelle Strava/Artefacts
- Modal de détail pour chaque élément
- Export et édition des artefacts

### Intégration Stripe (Future)
- Widget de paiement "pay as you go"
- Dashboard de consommation
- Alertes automatiques