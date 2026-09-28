"""
Définition des types d'artefacts générés pendant les conversations.
"""

from enum import Enum
from typing import Dict, Any

class ArtifactType(Enum):
    """Types d'artefacts générés par le modèle IA."""
    TRAINING_PLAN = "training_plan"
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    PERFORMANCE_REPORT = "performance_report"
    NUTRITION_ADVICE = "nutrition_advice"
    RECOVERY_GUIDANCE = "recovery_guidance"

class ArtifactMetadata:
    """Métadonnées pour un artefact."""
    
    def __init__(self, title: str, artifact_type: ArtifactType, 
                 related_activity_id: str = None):
        self.title = title
        self.type = artifact_type
        self.related_activity_id = related_activity_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit les métadonnées en dictionnaire."""
        return {
            'title': self.title,
            'type': self.type.value,
            'related_activity_id': self.related_activity_id
        }

# Templates de titres par type d'artefact
ARTIFACT_TITLE_TEMPLATES = {
    ArtifactType.TRAINING_PLAN: "Plan d'entraînement - {date}",
    ArtifactType.ANALYSIS: "Analyse de performance - {date}",
    ArtifactType.RECOMMENDATION: "Recommandations - {date}",
    ArtifactType.PERFORMANCE_REPORT: "Rapport de performance - {date}",
    ArtifactType.NUTRITION_ADVICE: "Conseils nutritionnels - {date}",
    ArtifactType.RECOVERY_GUIDANCE: "Guide de récupération - {date}"
}