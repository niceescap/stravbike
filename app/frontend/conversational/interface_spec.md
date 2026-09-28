# Spécification de l'Interface Conversational

## Structure de l'Application

L'application comporte deux onglets principaux :
1. **Interface de Chat Principal** - Conversation avec le coach IA
2. **Paramètres Utilisateur** - Gestion du compte et des artefacts

## Onglet 1: Chat Principal

### Composants UI
- **Zone d'affichage des messages** (scrollable)
  - Messages utilisateur (alignés à droite, couleur primaire)
  - Messages assistant (alignés à gauche, couleur secondaire)
  - Timestamp sur chaque message
  - Indicateur de typage ("Assistant est en train d'écrire...")
  
- **Zone de saisie de message**
  - Textarea multiligne avec redimensionnement automatique
  - Bouton d'envoi (Enter ou clic)
  - Indicateur de connexion
  
- **Barre d'état**
  - Statut de la session
  - Indicateur de génération d'artefacts

### Flux d'Interaction
1. L'utilisateur saisit un message
2. Le message est envoyé à l'API
3. Affichage d'un indicateur de chargement
4. Réception et affichage de la réponse
5. Création automatique d'artefacts si nécessaire
6. Notification utilisateur si artefacts générés

## Onglet 2: Paramètres Utilisateur

### Sections
1. **Profil Athlète**
   - Informations personnelles
   - Statistiques principales
   - Objectifs courants
   
2. **Activités Synchronisées**
   - Liste des dernières activités
   - Statistiques globales
   - Filtres par période
   
3. **Bibliothèque d'Artefacts**
   - Liste des plans de séance générés
   - Analyses de performance
   - Recommandations
   - Tri par date/type
   
4. **Gestion d'Abonnement**
   - Statut actuel
   - Options d'upgrade
   - Historique de facturation

## Gestion de Session

- **Réinitialisation automatique** : À chaque ouverture/refresh
- **Persistance** : Seuls les artefacts sont conservés
- **Isolement** : Chaque session est indépendante
- **Timeout** : Sessions expirées après 1 heure d'inactivité

## Design Principles

1. **Minimalisme** : Interface épurée, focus sur la conversation
2. **Fluidité** : Réponses instantanées, transitions smooth
3. **Accessibilité** : Contraste élevé, navigation clavier
4. **Responsive** : Adapté mobile/desktop
5. **Feedback** : Indicateurs visuels pour toutes les actions