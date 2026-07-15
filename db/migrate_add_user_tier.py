"""
db/migrate_add_user_tier.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Migration : ajoute les colonnes tier et llm_model à la table users.

À exécuter si la table users existe déjà (créée avant l'ajout du
système de niveaux LLM).

Usage :
    python db/migrate_add_user_tier.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from db.database import engine


def migrate():
    """Ajoute tier (NOT NULL, default 'free') et llm_model (NULL) à users."""
    with engine.connect() as conn:
        # Vérifier si les colonnes existent déjà
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
              AND column_name IN ('tier', 'llm_model')
        """))
        existing = {row[0] for row in result}

        if "tier" not in existing:
            print("➕ Ajout de la colonne tier...")
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'free'
            """))
            conn.commit()
            print("   ✅ tier ajouté (default: 'free' pour tous les utilisateurs existants)")
        else:
            print("♻️  Colonne tier déjà présente")

        if "llm_model" not in existing:
            print("➕ Ajout de la colonne llm_model...")
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN llm_model VARCHAR(100)
            """))
            conn.commit()
            print("   ✅ llm_model ajouté (NULL — utiliser le default du niveau)")
        else:
            print("♻️  Colonne llm_model déjà présente")

    print("\n✅ Migration terminée.")


if __name__ == "__main__":
    migrate()
