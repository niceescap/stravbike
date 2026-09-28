"""
Modèles pour les artefacts générés et l'unification des activités Strava/MD.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

class ArtifactType(Enum):
    """Types d'artefacts générés."""
    TRAINING_PLAN = "training_plan"
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    PERFORMANCE_REPORT = "performance_report"
    NUTRITION_ADVICE = "nutrition_advice"
    RECOVERY_GUIDANCE = "recovery_guidance"

class ActivitySourceType(Enum):
    """Sources des activités dans la liste unifiée."""
    STRAVA = "strava"
    ARTIFACT = "artifact"

@dataclass
class UnifiedActivity:
    """Représentation unifiée d'une activité Strava ou d'un artefact MD."""
    
    id: str  # UUID pour les artefacts, ID Strava pour les activités
    title: str
    date: datetime
    type: ArtifactType  # Pour les artefacts
    source_type: ActivitySourceType
    source_id: str  # ID original (Strava ou artifact)
    duration: Optional[int] = None  # En secondes
    distance: Optional[float] = None  # En mètres
    description: Optional[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'objet en dictionnaire pour la sérialisation."""
        result = asdict(self)
        result['date'] = self.date.isoformat()
        result['type'] = self.type.value if self.type else None
        result['source_type'] = self.source_type.value
        return result
    
    @classmethod
    def from_strava_activity(cls, strava_data: Dict[str, Any]) -> 'UnifiedActivity':
        """Crée une UnifiedActivity à partir des données Strava."""
        return cls(
            id=str(strava_data.get('id')),
            title=strava_data.get('name', 'Activité sans nom'),
            date=datetime.fromisoformat(strava_data.get('start_date').replace('Z', '+00:00')),
            type=None,  # Pas de type pour les activités Strava
            source_type=ActivitySourceType.STRAVA,
            source_id=str(strava_data.get('id')),
            duration=strava_data.get('elapsed_time'),
            distance=strava_data.get('distance'),
            description=strava_data.get('description'),
            tags=['strava', strava_data.get('sport_type', '').lower()]
        )
    
    @classmethod
    def from_artifact(cls, artifact_data: Dict[str, Any]) -> 'UnifiedActivity':
        """Crée une UnifiedActivity à partir des données d'artefact."""
        return cls(
            id=artifact_data.get('id'),
            title=artifact_data.get('title', 'Artefact sans titre'),
            date=datetime.fromisoformat(artifact_data.get('created_at').replace('Z', '+00:00')),
            type=ArtifactType(artifact_data.get('type')),
            source_type=ActivitySourceType.ARTIFACT,
            source_id=artifact_data.get('id'),
            description=artifact_data.get('content', '')[:200] + '...' if len(artifact_data.get('content', '')) > 200 else artifact_data.get('content', ''),
            tags=['artifact', artifact_data.get('type')]
        )

@dataclass
class Artifact:
    """Artefact généré par le modèle IA."""
    
    id: str  # UUID
    athlete_id: int
    title: str
    content: str  # Contenu Markdown
    type: ArtifactType
    related_activity_id: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'objet en dictionnaire pour la sérialisation."""
        result = asdict(self)
        result['type'] = self.type.value
        result['created_at'] = self.created_at.isoformat()
        result['updated_at'] = self.updated_at.isoformat()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Artifact':
        """Crée un Artifact à partir d'un dictionnaire."""
        # Convertir les chaînes ISO en datetime
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
        
        # Convertir le type
        if isinstance(data.get('type'), str):
            data['type'] = ArtifactType(data['type'])
        
        return cls(**data)

class ArtifactManager:
    """Gestionnaire des artefacts générés."""
    
    @staticmethod
    def create_artifact(athlete_id: int, title: str, content: str, 
                       artifact_type: ArtifactType, related_activity_id: str = None) -> Artifact:
        """Crée un nouvel artefact."""
        artifact = Artifact(
            id=None,  # Sera généré automatiquement
            athlete_id=athlete_id,
            title=title,
            content=content,
            type=artifact_type,
            related_activity_id=related_activity_id
        )
        
        # TODO: Sauvegarder dans la base de données
        print(f"Artefact créé: {title} ({artifact_type.value}) pour athlète {athlete_id}")
        return artifact
    
    @staticmethod
    def get_athlete_artifacts(athlete_id: int, limit: int = 50) -> List[Artifact]:
        """Récupère les artefacts d'un athlète."""
        # TODO: Implémenter la récupération depuis la BD
        # Pour l'instant, retourne une liste vide
        return []
    
    @staticmethod
    def get_artifact(artifact_id: str) -> Optional[Artifact]:
        """Récupère un artefact par son ID."""
        # TODO: Implémenter la récupération depuis la BD
        return None
    
    @staticmethod
    def get_unified_activities(athlete_id: int, limit: int = 50) -> List[UnifiedActivity]:
        """
        Récupère les activités unifiées (Strava + artefacts) triées par date.
        Cette méthode combine les données Strava et les artefacts pour l'affichage unifié.
        """
        unified_activities = []
        
        # TODO: Récupérer les vraies données
        # Pour l'instant, simulation
        
        # Simuler quelques activités Strava
        strava_activities = [
            {
                'id': '123456789',
                'name': 'Sortie entraînement matinale',
                'start_date': '2026-09-15T07:30:00Z',
                'elapsed_time': 3600,
                'distance': 45000,
                'description': 'Entraînement FTP 2x20min',
                'sport_type': 'Ride'
            },
            {
                'id': '123456790',
                'name': 'Course cyclo-cross',
                'start_date': '2026-09-14T10:00:00Z',
                'elapsed_time': 5400,
                'distance': 28000,
                'description': 'Compétition locale',
                'sport_type': 'Crossfit'
            }
        ]
        
        # Convertir les activités Strava
        for activity in strava_activities:
            unified_activities.append(UnifiedActivity.from_strava_activity(activity))
        
        # Simuler quelques artefacts
        artifacts = [
            {
                'id': 'art-001',
                'title': 'Plan d\'entraînement semaine 38',
                'created_at': '2026-09-15T18:00:00Z',
                'type': 'training_plan',
                'content': '# Plan d\'entraînement\\n\\n## Lundi\\n- Échauffement 20min\\n- FTP 2x20min'
            },
            {
                'id': 'art-002',
                'title': 'Analyse de performance - Sortie du 14/09',
                'created_at': '2026-09-14T20:30:00Z',
                'type': 'analysis',
                'content': '# Analyse de performance\\n\\n## Points forts\\n- Bonne puissance moyenne'
            }
        ]
        
        # Convertir les artefacts
        for artifact in artifacts:
            unified_activities.append(UnifiedActivity.from_artifact(artifact))
        
        # Trier par date (le plus récent en premier)
        unified_activities.sort(key=lambda x: x.date, reverse=True)
        
        return unified_activities[:limit]