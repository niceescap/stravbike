"""
Service d'intégration avec les modèles IA (OpenRouter, AlibabaCloud, etc.).
"""

import json
import httpx
from typing import Dict, List, Any, Optional
from datetime import datetime

class LLMIntegrationService:
    """Service d'intégration avec les modèles IA externes."""
    
    def __init__(self, api_base_url: str, api_key: str, model_name: str):
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.model_name = model_name
        self.client = httpx.AsyncClient()
    
    async def send_conversation_message(self, 
                                      athlete_context: Dict[str, Any],
                                      message_history: List[Dict[str, str]],
                                      current_message: str) -> Dict[str, Any]:
        """
        Envoie un message à l'assistant IA avec le contexte de l'athlète.
        """
        # Construction du prompt avec contexte
        system_prompt = self._build_system_prompt(athlete_context)
        
        # Préparation des messages pour l'API
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Ajout de l'historique
        messages.extend(message_history)
        
        # Ajout du message actuel
        messages.append({"role": "user", "content": current_message})
        
        # Appel à l'API externe
        try:
            response = await self._call_llm_api(messages)
            return self._process_llm_response(response)
        except Exception as e:
            return {
                "error": f"Erreur lors de la communication avec le modèle IA: {str(e)}",
                "response": "Désolé, je rencontre un problème technique. Pouvez-vous réessayer ?"
            }
    
    def _build_system_prompt(self, athlete_context: Dict[str, Any]) -> str:
        """Construit le prompt système avec le contexte de l'athlète."""
        profile = athlete_context.get('profile', {})
        stats = athlete_context.get('stats', {})
        
        prompt = f"""Tu es un coach sportif IA spécialisé dans le cyclisme. Tu accompagnes {profile.get('name', 'un athlète')}.

Informations importantes sur l'athlète:
- Âge: {profile.get('age', 'N/A')} ans
- Poids: {profile.get('weight', 'N/A')} kg
- FTP: {profile.get('ftp', 'N/A')} W

Ton rôle est d'aider l'athlète par la conversation. Tu peux:
1. Proposer des plans d'entraînement personnalisés
2. Analyser les performances récentes
3. Donner des conseils de récupération et de nutrition
4. Répondre aux questions techniques

Quand tu proposes un plan d'entraînement, génère un artefact Markdown qui sera sauvegardé.
Reste naturel, pédagogique et encourageant dans tes réponses."""

        return prompt
    
    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Appelle l'API du modèle IA."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        response = await self.client.post(
            f"{self.api_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30.0
        )
        
        response.raise_for_status()
        return response.json()
    
    def _process_llm_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Traite la réponse brute du modèle IA."""
        try:
            message_content = llm_response['choices'][0]['message']['content']
            
            return {
                "response": message_content,
                "timestamp": datetime.utcnow().isoformat()
            }
        except (KeyError, IndexError) as e:
            return {
                "error": f"Format de réponse invalide: {str(e)}",
                "response": "Désolé, j'ai rencontré un problème en traitant votre requête."
            }

# Instance du service
llm_service: Optional[LLMIntegrationService] = None

def initialize_llm_service(api_base_url: str, api_key: str, model_name: str):
    """Initialise le service d'intégration LLM."""
    global llm_service
    llm_service = LLMIntegrationService(api_base_url, api_key, model_name)