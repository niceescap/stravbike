"""
Service de suivi de la consommation de tokens par athlète.
"""

import tiktoken
from typing import Dict, Any, Optional
from datetime import datetime
from app.conversation.models.user_credits import TokenCreditManager, ModelInfo, AVAILABLE_MODELS
from app.conversation.models.artifacts import Artifact, ArtifactType

class TokenConsumptionTracker:
    """Suivi de la consommation de tokens pour chaque athlète."""
    
    def __init__(self):
        # Initialiser l'encodeur pour le comptage de tokens
        self.encoders = {}
    
    def _get_encoder(self, model_name: str):
        """Récupère ou crée un encodeur pour un modèle donné."""
        if model_name not in self.encoders:
            try:
                self.encoders[model_name] = tiktoken.encoding_for_model(model_name)
            except KeyError:
                # Fallback sur un encodeur générique
                self.encoders[model_name] = tiktoken.get_encoding("cl100k_base")
        return self.encoders[model_name]
    
    def count_tokens(self, text: str, model_name: str) -> int:
        """Compte le nombre de tokens dans un texte pour un modèle donné."""
        encoder = self._get_encoder(model_name)
        return len(encoder.encode(text))
    
    def track_consumption(self, athlete_id: int, model_name: str, 
                         input_text: str, output_text: str) -> Dict[str, Any]:
        """
        Suit la consommation de tokens pour une interaction avec le modèle.
        
        Args:
            athlete_id: ID de l'athlète
            model_name: Nom du modèle utilisé
            input_text: Texte d'entrée (prompt)
            output_text: Texte de sortie (réponse)
            
        Returns:
            Détails de la consommation
        """
        # Compter les tokens
        input_tokens = self.count_tokens(input_text, model_name)
        output_tokens = self.count_tokens(output_text, model_name)
        total_tokens = input_tokens + output_tokens
        
        # Trouver les informations du modèle
        model_info = None
        for model in AVAILABLE_MODELS:
            if model.name == model_name:
                model_info = model
                break
        
        if not model_info:
            # Modèle non trouvé, utiliser des valeurs par défaut
            cost_per_1k = 0.01
        else:
            cost_per_1k = model_info.cost_per_1k_tokens
        
        # Calculer le coût en unités de crédit
        cost_in_credits = (total_tokens / 1000) * cost_per_1k
        
        # Tenter de consommer les crédits
        success = TokenCreditManager.consume_tokens(athlete_id, int(cost_in_credits), model_name)
        
        # Préparer les détails de consommation
        consumption_details = {
            'athlete_id': athlete_id,
            'model_name': model_name,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'cost_in_credits': cost_in_credits,
            'success': success,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Logguer la consommation
        self._log_consumption(consumption_details)
        
        return consumption_details
    
    def _log_consumption(self, details: Dict[str, Any]):
        """Loggue la consommation dans la base de données."""
        # TODO: Implémenter l'enregistrement dans la BD
        print(f"Consommation enregistrée: Athlète {details['athlete_id']}, "
              f"Modèle {details['model_name']}, "
              f"Tokens: {details['total_tokens']}, "
              f"Coût: {details['cost_in_credits']:.4f} crédits")
    
    def get_athlete_consumption_summary(self, athlete_id: int) -> Dict[str, Any]:
        """
        Récupère un résumé de la consommation pour un athlète.
        
        Returns:
            Résumé de la consommation
        """
        # TODO: Implémenter la récupération depuis la BD
        # Pour l'instant, retourner des valeurs simulées
        return {
            'athlete_id': athlete_id,
            'total_tokens_used': 150000,  # Simulé
            'total_cost': 15.5,  # Simulé
            'models_usage': {
                'openai/gpt-4-turbo': {'tokens': 120000, 'cost': 12.0},
                'mistralai/mistral-7b-instruct': {'tokens': 30000, 'cost': 3.5}
            },
            'period': 'last_30_days'
        }

# Instance singleton du tracker
token_tracker = TokenConsumptionTracker()

# Service pour gérer les artefacts générés
class ArtifactGenerationService:
    """Service pour gérer la génération et le suivi des artefacts."""
    
    @staticmethod
    def create_training_plan_artifact(athlete_id: int, content: str, 
                                   related_activity_id: str = None) -> Artifact:
        """Crée un artefact de plan d'entraînement."""
        return Artifact(
            id=None,
            athlete_id=athlete_id,
            title=f"Plan d'entraînement - {datetime.now().strftime('%d/%m/%Y')}",
            content=content,
            type=ArtifactType.TRAINING_PLAN,
            related_activity_id=related_activity_id
        )
    
    @staticmethod
    def create_analysis_artifact(athlete_id: int, content: str, 
                              related_activity_id: str = None) -> Artifact:
        """Crée un artefact d'analyse."""
        return Artifact(
            id=None,
            athlete_id=athlete_id,
            title=f"Analyse de performance - {datetime.now().strftime('%d/%m/%Y')}",
            content=content,
            type=ArtifactType.ANALYSIS,
            related_activity_id=related_activity_id
        )
    
    @staticmethod
    def save_artifact(artifact: Artifact) -> bool:
        """
        Sauvegarde un artefact dans la base de données.
        
        Args:
            artifact: Artefact à sauvegarder
            
        Returns:
            True si la sauvegarde a réussi
        """
        # TODO: Implémenter la sauvegarde dans la BD
        print(f"Artefact sauvegardé: {artifact.title}")
        return True