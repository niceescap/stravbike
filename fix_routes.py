#!/usr/bin/env python3
"""
Retire l'import et l'utilisation de get_current_coach de tous les fichiers de routes.
Plus robuste qu'un script bash sed — utilise regex Python avec capture groups.
"""

import re
import sys
from pathlib import Path

FILES = [
    "api/routes/activities.py",
    "api/routes/calendar.py",
    "api/routes/comments.py",
    "api/routes/competitions.py",
    "api/routes/llm.py",
    "api/routes/sessions.py",
]

def clean_file(filepath):
    """Retire l'import et les dépendances get_current_coach d'un fichier."""
    p = Path(filepath)
    if not p.exists():
        print(f"⚠️  {filepath} introuvable, ignoré")
        return False

    with open(p, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    
    # 1. Retire l'import
    content = re.sub(
        r'from api\.routes\.auth import get_current_coach\n',
        '',
        content
    )
    
    # 2. Retire le paramètre coach dans les signatures de fonction
    # Cas 1: coach=Depends(get_current_coach), ... (au début)
    content = re.sub(
        r'coach\s*=\s*Depends\(get_current_coach\),\s*',
        '',
        content
    )
    
    # Cas 2: ..., coach=Depends(get_current_coach) (à la fin)
    content = re.sub(
        r',\s*coach\s*=\s*Depends\(get_current_coach\)',
        '',
        content
    )
    
    # Cas 3: coach=Depends(get_current_coach) seul (unique paramètre en plus de db)
    content = re.sub(
        r'coach\s*=\s*Depends\(get_current_coach\)',
        '',
        content
    )
    
    if content == original:
        print(f"ℹ️  {filepath} — aucun changement (probablement déjà propre)")
        return False
    
    # Sauvegarde et modification
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✅ {filepath} — modifié avec succès")
    return True

if __name__ == "__main__":
    print("=== Nettoyage des routes (retrait get_current_coach) ===\n")
    
    changed = 0
    for f in FILES:
        if clean_file(f):
            changed += 1
    
    print(f"\n=== Résumé : {changed} fichier(s) modifié(s) ===")
    
    if changed > 0:
        print("\n✅ Ensuite :")
        print("  git status              # vérifier")
        print("  git add -A")
        print("  git commit -m 'v3.2'")
        print("  Redémarrer le serveur")
    else:
        print("\n⚠️  Aucun changement. Vérifie les fichiers manuellement.")
