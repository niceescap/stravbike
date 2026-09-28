# Schéma de Base de Données Conversational

## Table: conversation_context
Stocke le contexte des discussions entre l'athlète et le coach IA.

- id (UUID) - Identifiant unique
- athlete_id (Integer) - Référence à l'athlète
- session_id (UUID) - Identifiant de session
- message_history (JSON) - Historique des messages
- created_at (Timestamp) - Date de création
- updated_at (Timestamp) - Date de dernière mise à jour

## Table: training_artifacts
Stocke les artefacts générés pendant les conversations (plans de séance, analyses, etc.).

- id (UUID) - Identifiant unique
- athlete_id (Integer) - Référence à l'athlète
- title (String) - Titre de l'artefact
- content (Text) - Contenu Markdown
- artifact_type (Enum) - Type d'artefact (training_plan, analysis, recommendation)
- related_activity_id (UUID) - Référence à une activité si applicable
- created_at (Timestamp) - Date de création
- updated_at (Timestamp) - Date de dernière mise à jour

## Table: llm_analyses
Stocke les analyses effectuées par le modèle IA.

- id (UUID) - Identifiant unique
- athlete_id (Integer) - Référence à l'athlète
- analysis_type (String) - Type d'analyse
- input_data (JSON) - Données d'entrée
- results (JSON) - Résultats de l'analyse
- related_artifact_id (UUID) - Référence à l'artefact généré
- created_at (Timestamp) - Date de création