"""  
Outil Open WebUI pour stravbike — v2 avec Valves + clé de service.  
  
L'outil appelle le backend FastAPI local (jamais Strava directement).  
Auth via clé de service statique (X-API-Key), configurable dans  
Open WebUI : Admin -> Tools -> stravbike -> Valves.  
  
Côté FastAPI, la route doit vérifier ce header, ex :  
  
    from fastapi import Header, HTTPException  
    import os  
  
    SERVICE_KEY = os.getenv("STRAVBIKE_SERVICE_KEY")  
  
    async def verify_service_key(x_api_key: str = Header(None)):  
        if not SERVICE_KEY or x_api_key != SERVICE_KEY:  
            raise HTTPException(status_code=401, detail="Invalid service key")  
  
    # puis sur chaque route : Depends(verify_service_key)  
"""  
  
import requests  
from pydantic import BaseModel, Field  
  
  
class Tools:  
    class Valves(BaseModel):  
        api_key: str = Field(  
            default="", description="Clé de service stravbike (X-API-Key)"  
        )  
        base_url: str = Field(  
            default="http://localhost:2024/api", description="URL du backend FastAPI"  
        )  
  
    def __init__(self):  
        self.valves = self.Valves()  
  
    def _headers(self) -> dict:  
        if not self.valves.api_key:  
            return {}  
        return {"X-API-Key": self.valves.api_key}  
  
    def _get(self, path: str, params: dict | None = None) -> str:  
        try:  
            r = requests.get(  
                f"{self.valves.base_url}{path}",  
                params=params,  
                headers=self._headers(),  
                timeout=10,  
            )  
            r.raise_for_status()  
            return r.text  
        except requests.RequestException as e:  
            return f"Erreur API stravbike ({path}): {e}"  
  
    def _post(self, path: str, json: dict | None = None) -> str:  
        try:  
            r = requests.post(  
                f"{self.valves.base_url}{path}",  
                json=json,  
                headers=self._headers(),  
                timeout=30,  
            )  
            r.raise_for_status()  
            return r.text  
        except requests.RequestException as e:  
            return f"Erreur API stravbike ({path}): {e}"  
  
    # ------------------------------------------------------------------  
    # Lecture (base de données uniquement, jamais d'appel Strava direct)  
    # ------------------------------------------------------------------  
  
    def get_athlete_profile(self) -> str:  
        """  
        Récupère le profil de l'athlète : FTP, poids, zones de puissance et cardio,  
        statistiques de la saison en cours. Données déjà synchronisées en base.  
        """  
        return self._get("/athlete")  
  
    def get_week_calendar(  
        self,  
        start_date: str = Field(  
            ..., description="Date de début de semaine, format YYYY-MM-DD"  
        ),  
    ) -> str:  
        """  
        Contenu complet d'une semaine : activités réalisées, séances planifiées,  
        compétitions, badges de validation.  
        """  
        return self._get("/calendar/week", params={"start_date": start_date})  
  
    def get_activity_detail(  
        self,  
        activity_id: int = Field(  
            ..., description="ID interne (base de données) de l'activité"  
        ),  
    ) -> str:  
        """  
        Détail complet d'une activité : distance, durée, puissance moyenne, FC,  
        Intensity Factor, TSS. Valeurs déjà calculées à l'ingestion.  
        """  
        return self._get(f"/activities/{activity_id}")  
  
    def get_competitions(self) -> str:  
        """  
        Liste des compétitions enregistrées (objectifs A/B/C) : dates, résultats  
        saisis manuellement, bilan post-course.  
        """  
        return self._get("/competitions")  
  
    def get_planned_sessions(  
        self,  
        week: str = Field(  
            ..., description="Semaine au format YYYY-MM-DD (lundi de la semaine)"  
        ),  
    ) -> str:  
        """  
        Séances planifiées par le coach pour une semaine donnée, avec statut de  
        validation (✅ / ❌ / ⏳).  
        """  
        return self._get("/sessions", params={"week": week})  
  
    # ------------------------------------------------------------------  
    # Écriture / action  
    # ------------------------------------------------------------------  
  
    def sync_latest_activities(self) -> str:  
        """  
        Déclenche une synchronisation incrémentale depuis Strava (nouvelles  
        activités seulement). À utiliser uniquement si l'utilisateur le demande  
        explicitement, jamais à chaque question.  
        """  
        return self._post("/activities/refresh")  
  
    def add_coach_comment(  
        self,  
        activity_id: int = Field(  
            ..., description="ID de l'activité ou de la séance concernée"  
        ),  
        comment: str = Field(..., description="Texte du commentaire"),  
    ) -> str:  
        """  
        Ajoute un commentaire coach ou athlète sur une activité donnée.  
        """  
        return self._post(  
            "/comments", json={"activity_id": activity_id, "comment": comment}  
        )  
