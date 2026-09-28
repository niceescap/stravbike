"""
Gestionnaire de sessions conversationnelles pour Stravbike.
Chaque session est isolée et réinitialisée à chaque ouverture/refresh.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class SessionManager:
    """Gère les sessions conversationnelles avec réinitialisation automatique."""
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = timedelta(hours=1)  # Timeout de session
    
    def create_session(self, athlete_id: int) -> str:
        """Crée une nouvelle session pour un athlète."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            'athlete_id': athlete_id,
            'created_at': datetime.utcnow(),
            'last_accessed': datetime.utcnow(),
            'message_history': []
        }
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Récupère une session existante avec vérification de timeout."""
        if session_id not in self.sessions:
            return None
            
        session = self.sessions[session_id]
        
        # Vérifier si la session a expiré
        if datetime.utcnow() - session['last_accessed'] > self.session_timeout:
            del self.sessions[session_id]
            return None
            
        # Mettre à jour le dernier accès
        session['last_accessed'] = datetime.utcnow()
        return session
    
    def add_message_to_session(self, session_id: str, role: str, content: str) -> bool:
        """Ajoute un message à l'historique d'une session."""
        session = self.get_session(session_id)
        if not session:
            return False
            
        session['message_history'].append({
            'role': role,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        })
        return True
    
    def reset_session(self, session_id: str) -> bool:
        """Réinitialise complètement une session."""
        if session_id not in self.sessions:
            return False
            
        session = self.sessions[session_id]
        session['message_history'] = []
        session['last_accessed'] = datetime.utcnow()
        return True
    
    def cleanup_expired_sessions(self):
        """Nettoie les sessions expirées."""
        now = datetime.utcnow()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if now - session['last_accessed'] > self.session_timeout
        ]
        
        for sid in expired_sessions:
            del self.sessions[sid]

# Instance singleton du gestionnaire de sessions
session_manager = SessionManager()