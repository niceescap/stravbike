"""
Initialise la base de données multi-athlète : crée toutes les tables.
À exécuter une fois au setup.
"""

from db.database import init_db

if __name__ == "__main__":
    init_db()
