"""
Composant frontend pour l'affichage unifié des activités Strava et des artefacts MD.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from app.conversation.models.artifacts import UnifiedActivity, ActivitySourceType, ArtifactType

class ActivityListRenderer:
    """Rendu de la liste unifiée d'activités et d'artefacts."""
    
    # Icônes pour différents types
    ICONS = {
        ActivitySourceType.STRAVA: "🚴",
        ActivitySourceType.ARTIFACT: "📝",
        ArtifactType.TRAINING_PLAN: "📋",
        ArtifactType.ANALYSIS: "📊",
        ArtifactType.RECOMMENDATION: "💡",
        ArtifactType.PERFORMANCE_REPORT: "📈",
        ArtifactType.NUTRITION_ADVICE: "🥗",
        ArtifactType.RECOVERY_GUIDANCE: "🛌"
    }
    
    # Couleurs pour différents types
    COLORS = {
        ActivitySourceType.STRAVA: "#FF4500",  # Orange vif pour Strava
        ActivitySourceType.ARTIFACT: "#4CAF50",  # Vert pour les artefacts
        ArtifactType.TRAINING_PLAN: "#2196F3",  # Bleu pour les plans
        ArtifactType.ANALYSIS: "#9C27B0",  # Violet pour les analyses
        ArtifactType.RECOMMENDATION: "#FF9800",  # Orange pour les recommandations
        ArtifactType.PERFORMANCE_REPORT: "#F44336",  # Rouge pour les rapports
        ArtifactType.NUTRITION_ADVICE: "#4CAF50",  # Vert pour la nutrition
        ArtifactType.RECOVERY_GUIDANCE: "#607D8B"   # Bleu-gris pour la récupération
    }
    
    def render_activity_list(self, activities: List[UnifiedActivity]) -> str:
        """
        Rendu HTML de la liste d'activités unifiées.
        
        Args:
            activities: Liste des activités unifiées triées par date
            
        Returns:
            Code HTML pour l'affichage de la liste
        """
        if not activities:
            return "<div class='empty-state'>Aucune activité ou artefact à afficher</div>"
        
        html = [
            "<div class='activity-list'>",
            "<div class='activity-list-header'>",
            "<h3>Activités et Plans</h3>",
            "<div class='sort-controls'>",
            "<button onclick='sortActivities(\"date\")' class='active'>📅 Date</button>",
            "<button onclick='sortActivities(\"type\")'>🏷️ Type</button>",
            "</div>",
            "</div>",
            "<div class='activity-items'>"
        ]
        
        for activity in activities:
            html.append(self._render_activity_item(activity))
        
        html.append("</div>")
        html.append("</div>")
        
        return "\n".join(html)
    
    def _render_activity_item(self, activity: UnifiedActivity) -> str:
        """Rendu d'un élément d'activité individuel."""
        icon = self._get_icon(activity)
        color = self._get_color(activity)
        formatted_date = activity.date.strftime("%d/%m/%Y %H:%M")
        duration_str = self._format_duration(activity.duration) if activity.duration else ""
        distance_str = self._format_distance(activity.distance) if activity.distance else ""
        
        # Description tronquée
        description = activity.description or ""
        if len(description) > 100:
            description = description[:100] + "..."
        
        # Tags formatés
        tags_html = "".join([f"<span class='tag'>{tag}</span>" for tag in activity.tags[:3]])
        
        html = f"""
        <div class="activity-item" data-id="{activity.id}" data-source="{activity.source_type.value}" 
             onclick="showActivityDetail('{activity.id}', '{activity.source_type.value}')">
            <div class="activity-icon" style="color: {color};">{icon}</div>
            <div class="activity-content">
                <div class="activity-header">
                    <h4 class="activity-title">{activity.title}</h4>
                    <span class="activity-date">{formatted_date}</span>
                </div>
                <div class="activity-meta">
                    <span class="activity-duration">{duration_str}</span>
                    <span class="activity-distance">{distance_str}</span>
                </div>
                <div class="activity-description">{description}</div>
                <div class="activity-tags">{tags_html}</div>
            </div>
        </div>
        """
        
        return html
    
    def _get_icon(self, activity: UnifiedActivity) -> str:
        """Récupère l'icône appropriée pour une activité."""
        if activity.source_type == ActivitySourceType.STRAVA:
            return self.ICONS[ActivitySourceType.STRAVA]
        elif activity.type:
            return self.ICONS.get(activity.type, self.ICONS[ActivitySourceType.ARTIFACT])
        else:
            return self.ICONS[ActivitySourceType.ARTIFACT]
    
    def _get_color(self, activity: UnifiedActivity) -> str:
        """Récupère la couleur appropriée pour une activité."""
        if activity.source_type == ActivitySourceType.STRAVA:
            return self.COLORS[ActivitySourceType.STRAVA]
        elif activity.type:
            return self.COLORS.get(activity.type, self.COLORS[ActivitySourceType.ARTIFACT])
        else:
            return self.COLORS[ActivitySourceType.ARTIFACT]
    
    def _format_duration(self, seconds: int) -> str:
        """Formate une durée en secondes en chaîne lisible."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h{minutes:02d}"
        else:
            return f"{minutes}min"
    
    def _format_distance(self, meters: float) -> str:
        """Formate une distance en mètres en chaîne lisible."""
        if meters >= 1000:
            return f"{meters/1000:.1f}km"
        else:
            return f"{int(meters)}m"
    
    def render_activity_detail_modal(self, activity: UnifiedActivity) -> str:
        """
        Rendu du modal de détail pour une activité ou un artefact.
        
        Args:
            activity: Activité ou artefact à afficher en détail
            
        Returns:
            Code HTML pour le modal de détail
        """
        icon = self._get_icon(activity)
        color = self._get_color(activity)
        formatted_date = activity.date.strftime("%d/%m/%Y à %H:%M")
        
        # Déterminer le type d'affichage
        if activity.source_type == ActivitySourceType.STRAVA:
            content_type = "Activité Strava"
            source_info = f"ID Strava: {activity.source_id}"
        else:
            content_type = f"Artefact - {activity.type.value.replace('_', ' ').title()}"
            source_info = f"ID: {activity.source_id}"
        
        # Contenu spécifique
        if activity.source_type == ActivitySourceType.STRAVA:
            # Pour les activités Strava, afficher les détails techniques
            content_html = f"""
            <div class="strava-activity-detail">
                <div class="detail-row">
                    <span class="label">Durée:</span>
                    <span class="value">{self._format_duration(activity.duration)}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Distance:</span>
                    <span class="value">{self._format_distance(activity.distance)}</span>
                </div>
                <div class="detail-row">
                    <span class="label">Description:</span>
                    <span class="value">{activity.description or 'Aucune description'}</span>
                </div>
                <div class="actions">
                    <button class="btn-primary" onclick="openInStrava('{activity.source_id}')">
                        🚴 Voir dans Strava
                    </button>
                </div>
            </div>
            """
        else:
            # Pour les artefacts, afficher le contenu Markdown
            content_html = f"""
            <div class="artifact-detail">
                <div class="markdown-content">
                    {self._render_markdown_preview(activity.description)}
                </div>
                <div class="actions">
                    <button class="btn-primary" onclick="downloadArtifact('{activity.id}')">
                        📥 Télécharger (MD)
                    </button>
                    <button class="btn-secondary" onclick="editArtifact('{activity.id}')">
                        ✏️ Éditer
                    </button>
                </div>
            </div>
            """
        
        html = f"""
        <div id="activity-detail-modal" class="modal" style="display: block;">
            <div class="modal-content">
                <div class="modal-header">
                    <h2><span style="color: {color};">{icon}</span> {activity.title}</h2>
                    <span class="close" onclick="closeModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <div class="activity-info">
                        <div class="info-item">
                            <strong>Type:</strong> {content_type}
                        </div>
                        <div class="info-item">
                            <strong>Date:</strong> {formatted_date}
                        </div>
                        <div class="info-item">
                            <strong>Source:</strong> {source_info}
                        </div>
                    </div>
                    {content_html}
                </div>
            </div>
        </div>
        """
        
        return html
    
    def _render_markdown_preview(self, content: str) -> str:
        """Rendu simplifié du contenu Markdown."""
        # Remplacement basique des éléments Markdown
        html = content.replace("\n\n", "</p><p>")
        html = html.replace("**", "<strong>").replace("__", "<strong>")
        html = html.replace("*", "<em>").replace("_", "<em>")
        html = html.replace("# ", "<h3>").replace("\n#", "\n<h3>")
        html = html.replace("## ", "<h4>").replace("\n##", "\n<h4>")
        html = f"<p>{html}</p>"
        return html

# Instance du renderer
activity_renderer = ActivityListRenderer()