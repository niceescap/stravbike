"""
ingestion/ingest_users_and_athletes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ingestion des tokens Strava stockés en JSON vers la base multi-athlète.

Scanne <projet>/data/tokens/*.json (créés par auth/main.py) et crée
les enregistrements User + Athlete correspondants.

Le script est idempotent :
  - Ignore les JSON déjà traités (mêmes tokens)
  - Met à jour les tokens s'ils ont changé
  - Met à jour les emails des athlètes existants si le JSON en contient un
  - L'email doit être présent dans le JSON (ajouté par auth/main.py v2)

Usage :
    python -m ingestion.ingest_users_and_athletes
    python -m ingestion.ingest_users_and_athletes /chemin/vers/tokens
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# Ajoute la racine du projet au path pour les imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import User, Athlete


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def get_token_files(tokens_dir: Path) -> List[Path]:
    """Récupère tous les fichiers .json du dossier tokens, triés par nom."""
    if not tokens_dir.exists():
        print(f"❌ Le dossier {tokens_dir} n'existe pas.")
        return []
    return sorted(tokens_dir.glob("*.json"))


def load_token_json(filepath: Path) -> Optional[Dict]:
    """Charge et parse un fichier JSON de token."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Erreur lecture {filepath}: {e}")
        return None


def parse_expires_at(expires_at_unix: Optional[int]) -> Optional[datetime]:
    """Convertit un timestamp Unix en datetime."""
    if not expires_at_unix:
        return None
    try:
        return datetime.fromtimestamp(int(expires_at_unix))
    except Exception as e:
        print(f"⚠ Erreur parsing expires_at ({expires_at_unix}): {e}")
        return None


# ────────────────────────────────────────────────────────────────────────────
# Cœur métier : UPSERT User + Athlete
# ────────────────────────────────────────────────────────────────────────────

def upsert_user_and_athlete(
    db: Session,
    token_data: Dict,
) -> Tuple[bool, str]:
    """
    UPSERT un User + Athlete à partir des données d'un token JSON.

    L'email doit être présent dans le JSON (ajouté par auth/main.py v2).

    Retourne : (success: bool, message: str)
    """
    # Extraction des données
    athlete_id_strava = token_data.get("athlete_id")
    firstname = token_data.get("firstname", "Unknown")
    lastname = token_data.get("lastname", "Unknown")
    profile_pic_url = token_data.get("profile_pic_url")
    refresh_token = token_data.get("refresh_token")
    expires_at_unix = token_data.get("expires_at")
    email = token_data.get("email")  # ✅ Email saisi via le formulaire OAuth

    if not athlete_id_strava or not refresh_token:
        return False, "❌ Token incomplet (athlete_id ou refresh_token manquant)"

    if not email:
        # Rétro-compatible : si pas d'email, on skip proprement
        return True, "⏭️ Skipped (email manquant dans le JSON — ancien token)"

    # Parse expiry
    token_expires_at = parse_expires_at(expires_at_unix)

    try:
        # ── 1. Cherche ou crée l'User par email ──
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                firstname=firstname,
                lastname=lastname,
                password_hash=None,  # Auth externe (OAuth Strava)
            )
            db.add(user)
            db.flush()
            msg = f"✨ User créé: {email}"
        else:
            # Mise à jour des prénoms/noms si changés
            if user.firstname != firstname:
                user.firstname = firstname
            if user.lastname != lastname:
                user.lastname = lastname
            msg = f"♻️ User existant: {email}"

        # ── 2. Cherche ou crée l'Athlete ──
        athlete = db.query(Athlete).filter(
            Athlete.owner_user_id == user.id,
            Athlete.strava_id == athlete_id_strava,
        ).first()

        if not athlete:
            athlete = Athlete(
                strava_id=athlete_id_strava,
                firstname=firstname,
                lastname=lastname,
                profile_pic_url=profile_pic_url,
                owner_user_id=user.id,
                strava_refresh_token=refresh_token,
                strava_token_expires_at=token_expires_at,
                ftp_watts=237,
                weight_kg=71.0,
            )
            db.add(athlete)
            msg += f" | ✨ Athlete créé: {firstname} {lastname} (Strava ID: {athlete_id_strava})"
        else:
            # Mise à jour du token (même si identique — idempotent)
            athlete.strava_refresh_token = refresh_token
            athlete.strava_token_expires_at = token_expires_at
            # Mise à jour des infos profil
            athlete.firstname = firstname
            athlete.lastname = lastname
            athlete.profile_pic_url = profile_pic_url
            msg += f" | ♻️ Athlete updated: {firstname} {lastname}"

        db.commit()
        return True, msg

    except Exception as e:
        db.rollback()
        return False, f"❌ Erreur ingestion pour {firstname} {lastname}: {e}"


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ────────────────────────────────────────────────────────────────────────────

def main(tokens_dir: Optional[Path] = None):
    """Scanne et ingère tous les tokens du dossier data/tokens/."""

    if tokens_dir is None:
        tokens_dir = Path(__file__).resolve().parent.parent / "data" / "tokens"

    print(f"🔍 Scan des tokens dans {tokens_dir}")
    print("-" * 80)

    token_files = get_token_files(tokens_dir)
    if not token_files:
        print("❌ Aucun fichier JSON trouvé.")
        return

    print(f"📦 {len(token_files)} fichier(s) trouvé(s):")
    for f in token_files:
        print(f"   - {f.name}")
    print("-" * 80)

    db = SessionLocal()
    results: List[Tuple[str, bool, str]] = []

    try:
        for token_file in token_files:
            print(f"\n📄 Traitement {token_file.name}...")

            token_data = load_token_json(token_file)
            if not token_data:
                results.append((token_file.name, False, "❌ JSON illisible"))
                continue

            success, message = upsert_user_and_athlete(db, token_data)
            results.append((token_file.name, success, message))
            print(f"   {message}")

    finally:
        db.close()

    # ── Rapport final ──
    print("\n" + "=" * 80)
    print("📋 RAPPORT D'INGESTION")
    print("=" * 80)

    success_count = sum(1 for _, s, _ in results if s)
    skip_count = sum(1 for _, s, m in results if s and "Skipped" in m)
    fail_count = len(results) - success_count

    for filename, success, message in results:
        status = "✅" if success else "❌"
        print(f"{status} {filename}: {message}")

    print("-" * 80)
    print(f"✅ Succès: {success_count}/{len(results)}")
    if skip_count > 0:
        print(f"⏭️ Skipped (email manquant): {skip_count}/{len(results)}")
    if fail_count > 0:
        print(f"❌ Erreurs: {fail_count}/{len(results)}")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(Path(sys.argv[1]))
    else:
        main()
