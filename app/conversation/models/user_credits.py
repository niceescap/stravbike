"""
Modèles pour la gestion des crédits et de la consommation de tokens.
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

class ModelProvider(Enum):
    """Providers de modèles IA disponibles."""
    OPENROUTER = "openrouter"
    ALIBABACLOUD = "alibabacloud"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

@dataclass
class ModelInfo:
    """Information sur un modèle IA."""
    name: str
    provider: ModelProvider
    display_name: str
    description: str
    cost_per_1k_tokens: float  # Coût en unités de crédit par 1000 tokens
    max_tokens: int
    is_default: bool = False

# Modèles disponibles
AVAILABLE_MODELS = [
    ModelInfo(
        name="mistralai/mistral-7b-instruct",
        provider=ModelProvider.OPENROUTER,
        display_name="Mistral 7B (Économique)",
        description="Modèle léger et économique, idéal pour les conversations simples",
        cost_per_1k_tokens=0.001,
        max_tokens=8192
    ),
    ModelInfo(
        name="openai/gpt-4-turbo",
        provider=ModelProvider.OPENROUTER,
        display_name="GPT-4 Turbo",
        description="Modèle haute performance pour des analyses complexes",
        cost_per_1k_tokens=0.03,
        max_tokens=128000,
        is_default=True
    ),
    ModelInfo(
        name="claude-3-haiku",
        provider=ModelProvider.ANTHROPIC,
        display_name="Claude 3 Haiku",
        description="Équilibré entre performance et coût",
        cost_per_1k_tokens=0.002,
        max_tokens=200000
    ),
    ModelInfo(
        name="qwen-max",
        provider=ModelProvider.ALIBABACLOUD,
        display_name="Qwen Max",
        description="Modèle multilingue avancé",
        cost_per_1k_tokens=0.005,
        max_tokens=32768
    )
]

class TokenCreditManager:
    """Gestionnaire des crédits de tokens pour les utilisateurs."""
    
    # Crédit de départ pour un nouvel utilisateur (en tokens)
    DEFAULT_CREDIT = 2_000_000  # 2M tokens
    
    # Limite d'affichage de la jauge (100% = 2M tokens)
    GAUGE_MAX = 2_000_000
    
    @staticmethod
    def get_user_credit(athlete_id: int) -> int:
        """
        Récupère le crédit restant d'un utilisateur.
        Dans l'implémentation finale, cela viendra de la base de données.
        """
        # TODO: Implémenter la récupération depuis la BD
        # Pour l'instant, retourne le crédit par défaut
        return TokenCreditManager.DEFAULT_CREDIT
    
    @staticmethod
    def consume_tokens(athlete_id: int, tokens_used: int, model_name: str) -> bool:
        """
        Consomme des tokens du crédit de l'utilisateur.
        
        Args:
            athlete_id: ID de l'athlète
            tokens_used: Nombre de tokens consommés
            model_name: Nom du modèle utilisé
            
        Returns:
            True si la consommation a réussi, False sinon
        """
        # TODO: Implémenter la logique de consommation dans la BD
        # Pour l'instant, simulation
        current_credit = TokenCreditManager.get_user_credit(athlete_id)
        if current_credit >= tokens_used:
            # Simuler la mise à jour de la BD
            print(f"Athlète {athlete_id}: {tokens_used} tokens consommés sur le modèle {model_name}")
            return True
        return False
    
    @staticmethod
    def add_credit(athlete_id: int, tokens_added: int) -> bool:
        """
        Ajoute des tokens au crédit de l'utilisateur.
        Utilisé par le script d'administration.
        """
        # TODO: Implémenter l'ajout de crédit dans la BD
        print(f"Ajout de {tokens_added} tokens pour l'athlète {athlete_id}")
        return True
    
    @staticmethod
    def get_credit_percentage(athlete_id: int) -> float:
        """Calcule le pourcentage de crédit restant pour la jauge."""
        current_credit = TokenCreditManager.get_user_credit(athlete_id)
        return min(100.0, (current_credit / TokenCreditManager.GAUGE_MAX) * 100)

# Script d'administration pour ajouter des crédits
ADMIN_SCRIPT_TEMPLATE = '''
#!/usr/bin/env python3
"""
Script d'administration pour ajouter des crédits aux athlètes.
"""

import sys
from app.conversation.models.user_credits import TokenCreditManager

def main():
    # Liste des athlètes disponibles
    athletes = [
        {"id": 139461126, "name": "Lazare Scapino"},
        # Ajouter d'autres athlètes ici
    ]
    
    print("=== Script d'ajout de crédits ===")
    print("\\nAthlètes disponibles:")
    for i, athlete in enumerate(athletes):
        print(f"{i+1}. {athlete['name']} (ID: {athlete['id']})")
    
    try:
        choice = int(input("\\nSélectionnez un athlète (numéro): ")) - 1
        if choice < 0 or choice >= len(athletes):
            print("Choix invalide")
            return
            
        athlete = athletes[choice]
        tokens = int(input("Nombre de tokens à ajouter: "))
        
        if TokenCreditManager.add_credit(athlete['id'], tokens):
            print(f"✅ {tokens} tokens ajoutés à {athlete['name']}")
        else:
            print("❌ Erreur lors de l'ajout des tokens")
            
    except ValueError:
        print("Veuillez entrer des nombres valides")
    except KeyboardInterrupt:
        print("\\nOpération annulée")

if __name__ == "__main__":
    main()
'''