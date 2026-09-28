"""
Composant frontend pour la jauge de crédits et la sélection des modèles.
"""

from typing import List, Dict, Any
from app.conversation.models.user_credits import TokenCreditManager, ModelInfo, AVAILABLE_MODELS

class CreditWidgetRenderer:
    """Rendu du widget de crédits et de sélection de modèle."""
    
    def render_credit_gauge(self, athlete_id: int) -> str:
        """
        Rendu de la jauge de crédits de l'utilisateur.
        
        Args:
            athlete_id: ID de l'athlète
            
        Returns:
            Code HTML pour la jauge de crédits
        """
        current_credit = TokenCreditManager.get_user_credit(athlete_id)
        percentage = TokenCreditManager.get_credit_percentage(athlete_id)
        gauge_max = TokenCreditManager.GAUGE_MAX
        
        # Formatage des nombres
        current_formatted = self._format_tokens(current_credit)
        max_formatted = self._format_tokens(gauge_max)
        
        # Couleur de la jauge selon le niveau
        gauge_color = self._get_gauge_color(percentage)
        
        html = f"""
        <div class="credit-widget">
            <div class="credit-header">
                <h3>💰 Crédits d'Inférence</h3>
                <span class="credit-refresh" onclick="refreshCredits()" title="Actualiser">
                    🔄
                </span>
            </div>
            
            <div class="credit-gauge-container">
                <div class="credit-gauge">
                    <div class="gauge-fill" style="width: {percentage}%; background-color: {gauge_color};"></div>
                    <div class="gauge-marker" style="left: {min(percentage, 100)}%;"></div>
                </div>
                
                <div class="credit-text">
                    <span class="credit-current">{current_formatted}</span>
                    <span class="credit-max">/ {max_formatted}</span>
                </div>
                
                <div class="credit-percentage">
                    {percentage:.1f}% du quota mensuel
                </div>
            </div>
            
            <div class="credit-info">
                <small>Les crédits sont renouvelés le 1er de chaque mois</small>
            </div>
        </div>
        """
        
        return html
    
    def render_model_selector(self, athlete_id: int, current_model: str = None) -> str:
        """
        Rendu du sélecteur de modèle IA.
        
        Args:
            athlete_id: ID de l'athlète
            current_model: Nom du modèle actuellement sélectionné
            
        Returns:
            Code HTML pour le sélecteur de modèle
        """
        if not current_model:
            # Trouver le modèle par défaut
            default_model = next((m for m in AVAILABLE_MODELS if m.is_default), AVAILABLE_MODELS[0])
            current_model = default_model.name
        
        html = [
            "<div class='model-selector'>",
            "<div class='model-header'>",
            "<h3>🤖 Modèle d'Assistant</h3>",
            "</div>",
            "<div class='model-selection'>",
            "<select id='model-selector' onchange='changeModel(this.value)'>"
        ]
        
        # Ajouter chaque modèle disponible
        for model in AVAILABLE_MODELS:
            selected = "selected" if model.name == current_model else ""
            cost_info = f"({model.cost_per_1k_tokens:.4f} crédits/1K tokens)"
            
            html.append(f"""
            <option value="{model.name}" {selected} data-provider="{model.provider.value}">
                {model.display_name} {cost_info}
                { " ★" if model.is_default else ""}
            </option>
            """)
        
        html.append("</select>")
        html.append("</div>")
        
        # Informations sur le modèle sélectionné
        current_model_info = next((m for m in AVAILABLE_MODELS if m.name == current_model), None)
        if current_model_info:
            html.append(self._render_model_info(current_model_info))
        
        html.append("</div>")
        
        return "\n".join(html)
    
    def _render_model_info(self, model: ModelInfo) -> str:
        """Rendu des informations détaillées sur un modèle."""
        provider_name = model.provider.value.title()
        
        html = f"""
        <div class="model-info">
            <div class="model-description">
                <strong>Description:</strong> {model.description}
            </div>
            <div class="model-details">
                <span class="detail-item">
                    <strong>Fournisseur:</strong> {provider_name}
                </span>
                <span class="detail-item">
                    <strong>Contexte max:</strong> {model.max_tokens:,} tokens
                </span>
                <span class="detail-item">
                    <strong>Coût:</strong> {model.cost_per_1k_tokens:.4f} crédits/1K tokens
                </span>
            </div>
        </div>
        """
        
        return html
    
    def _format_tokens(self, tokens: int) -> str:
        """Formate le nombre de tokens de manière lisible."""
        if tokens >= 1_000_000:
            return f"{tokens/1_000_000:.1f}M"
        elif tokens >= 1_000:
            return f"{tokens/1_000:.1f}k"
        else:
            return str(tokens)
    
    def _get_gauge_color(self, percentage: float) -> str:
        """Détermine la couleur de la jauge selon le pourcentage."""
        if percentage < 50:
            return "#4CAF50"  # Vert
        elif percentage < 80:
            return "#FF9800"  # Orange
        else:
            return "#F44336"  # Rouge

class AthleteProfileRenderer:
    """Rendu du profil athlète dans les paramètres."""
    
    def render_athlete_profile(self, athlete_data: Dict[str, Any]) -> str:
        """
        Rendu du profil athlète.
        
        Args:
            athlete_data: Données du profil athlète
            
        Returns:
            Code HTML pour l'affichage du profil
        """
        profile = athlete_data.get('profile', {})
        stats = athlete_data.get('stats', {})
        
        html = f"""
        <div class="athlete-profile">
            <div class="profile-header">
                <h3>👤 Profil Athlète</h3>
            </div>
            
            <div class="profile-content">
                <div class="profile-section">
                    <h4>Informations Personnelles</h4>
                    <div class="profile-item">
                        <span class="label">Nom:</span>
                        <span class="value">{profile.get('name', 'Non renseigné')}</span>
                    </div>
                    <div class="profile-item">
                        <span class="label">Âge:</span>
                        <span class="value">{profile.get('age', 'N/A')} ans</span>
                    </div>
                    <div class="profile-item">
                        <span class="label">Poids:</span>
                        <span class="value">{profile.get('weight', 'N/A')} kg</span>
                    </div>
                </div>
                
                <div class="profile-section">
                    <h4>Paramètres Sportifs</h4>
                    <div class="profile-item">
                        <span class="label">FTP:</span>
                        <span class="value">{profile.get('ftp', 'N/A')} W</span>
                    </div>
                    <div class="profile-item">
                        <span class="label">Seuil lactique:</span>
                        <span class="value">{profile.get('lactate_threshold', 'N/A')} W</span>
                    </div>
                </div>
                
                <div class="profile-section">
                    <h4>Statistiques Récentes</h4>
                    <div class="profile-item">
                        <span class="label">Distance totale:</span>
                        <span class="value">{stats.get('total_distance', 0):,.0f} km</span>
                    </div>
                    <div class="profile-item">
                        <span class="label">Temps total:</span>
                        <span class="value">{self._format_hours(stats.get('total_time', 0))}</span>
                    </div>
                    <div class="profile-item">
                        <span class="label">Dénivelé positif:</span>
                        <span class="value">{stats.get('total_elevation', 0):,.0f} m</span>
                    </div>
                </div>
            </div>
        </div>
        """
        
        return html
    
    def _format_hours(self, seconds: int) -> str:
        """Formate un nombre de secondes en heures."""
        hours = seconds / 3600
        return f"{hours:.1f} heures"

# Instances des renderers
credit_renderer = CreditWidgetRenderer()
profile_renderer = AthleteProfileRenderer()