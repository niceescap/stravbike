"""
ingestion/set_user_tier.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
CLI d'administration pour gérer les niveaux LLM des utilisateurs.

Permet à l'admin de :
  - Changer le niveau d'un utilisateur (free / supporter / donor)
  - Attribuer un modèle spécifique à un utilisateur
  - Lister les utilisateurs et leurs modèles actuels
  - Voir les modèles disponibles par niveau

Usage :
    # Lister tous les utilisateurs avec leur niveau
    python -m ingestion.set_user_tier list

    # Voir les modèles disponibles par niveau
    python -m ingestion.set_user_tier tiers

    # Changer le niveau d'un utilisateur
    python -m ingestion.set_user_tier set-tier --email jean@example.com --tier supporter

    # Attribuer un modèle spécifique
    python -m ingestion.set_user_tier set-model --email jean@example.com --model openai/gpt-4o

    # Réinitialiser le modèle au default du niveau
    python -m ingestion.set_user_tier reset-model --email jean@example.com
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
from tabulate import tabulate
from db.database import SessionLocal
from db.models import User
from services.llm_router import (
    LLM_REGISTRY,
    VALID_TIERS,
    get_tier_for_user,
    set_user_tier,
    set_user_model,
    get_all_tiers_info,
)


# ────────────────────────────────────────────────────────────────────────────
# Commande : list
# ────────────────────────────────────────────────────────────────────────────

def cmd_list(db: Session):
    """Liste tous les utilisateurs avec leur niveau et modèle."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    if not users:
        print("Aucun utilisateur trouvé.")
        return

    rows = []
    for u in users:
        tier_info = get_tier_for_user(db, u.id)
        rows.append([
            u.id,
            u.email,
            f"{u.firstname or ''} {u.lastname or ''}".strip() or "—",
            tier_info["label"],
            tier_info["current_model"],
            u.last_login_at.strftime("%Y-%m-%d") if u.last_login_at else "Jamais",
        ])

    print(tabulate(
        rows,
        headers=["ID", "Email", "Nom", "Niveau", "Modèle LLM", "Dernière connexion"],
        tablefmt="simple_outline",
    ))
    print(f"\nTotal: {len(users)} utilisateur(s)")


# ────────────────────────────────────────────────────────────────────────────
# Commande : tiers
# ────────────────────────────────────────────────────────────────────────────

def cmd_tiers():
    """Affiche les modèles disponibles par niveau."""
    info = get_all_tiers_info()

    for tier, data in info.items():
        print(f"\n{'─' * 60}")
        print(f"  {data['label'].upper()} — {data['description']}")
        print(f"{'─' * 60}")
        print(f"  Default : {data['default_model']}")
        print(f"  Choix   : {data['model_count']} modèle(s) disponible(s)")
        for i, model in enumerate(data["available_models"], 1):
            marker = " ← default" if model == data["default_model"] else ""
            print(f"    {i}. {model}{marker}")

    print(f"\n{'─' * 60}")
    print(f"  Niveaux valides : {', '.join(VALID_TIERS)}")


# ────────────────────────────────────────────────────────────────────────────
# Commande : set-tier
# ────────────────────────────────────────────────────────────────────────────

def cmd_set_tier(db: Session, email: str, tier: str, model: str = None):
    """Change le niveau d'un utilisateur."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print(f"❌ Utilisateur '{email}' introuvable.")
        return

    try:
        result = set_user_tier(db, user.id, tier, model_id=model)
        print(f"✅ Niveau changé pour {result['email']} :")
        print(f"   Ancien niveau : {result['old_tier']}")
        print(f"   Nouveau niveau : {result['new_tier']}")
        print(f"   Modèle attribué : {result['model']}")
    except ValueError as e:
        print(f"❌ Erreur : {e}")


# ────────────────────────────────────────────────────────────────────────────
# Commande : set-model
# ────────────────────────────────────────────────────────────────────────────

def cmd_set_model(db: Session, email: str, model: str):
    """Attribue un modèle spécifique à un utilisateur."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print(f"❌ Utilisateur '{email}' introuvable.")
        return

    try:
        result = set_user_model(db, user.id, model)
        print(f"✅ Modèle attribué à {result['email']} :")
        print(f"   Niveau : {result['tier']}")
        print(f"   Modèle : {result['model']}")
    except ValueError as e:
        print(f"❌ Erreur : {e}")


# ────────────────────────────────────────────────────────────────────────────
# Commande : reset-model
# ────────────────────────────────────────────────────────────────────────────

def cmd_reset_model(db: Session, email: str):
    """Réinitialise le modèle au default du niveau de l'utilisateur."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print(f"❌ Utilisateur '{email}' introuvable.")
        return

    tier_info = get_tier_for_user(db, user.id)
    user.llm_model = None  # NULL → le routeur utilisera le default du niveau
    db.commit()

    print(f"✅ Modèle réinitialisé pour {user.email} :")
    print(f"   Niveau : {tier_info['tier']}")
    print(f"   Nouveau modèle (default) : {tier_info['current_model']}")


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée CLI
# ────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gestion des niveaux LLM des utilisateurs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commande à exécuter")

    # ── list ──
    subparsers.add_parser("list", help="Lister tous les utilisateurs")

    # ── tiers ──
    subparsers.add_parser("tiers", help="Voir les modèles par niveau")

    # ── set-tier ──
    p_set_tier = subparsers.add_parser("set-tier", help="Changer le niveau d'un utilisateur")
    p_set_tier.add_argument("--email", required=True, help="Email de l'utilisateur")
    p_set_tier.add_argument(
        "--tier", required=True, choices=VALID_TIERS, help="Niveau à attribuer"
    )
    p_set_tier.add_argument(
        "--model", default=None, help="Modèle spécifique (optionnel, doit être dans le niveau)"
    )

    # ── set-model ──
    p_set_model = subparsers.add_parser("set-model", help="Attribuer un modèle spécifique")
    p_set_model.add_argument("--email", required=True, help="Email de l'utilisateur")
    p_set_model.add_argument("--model", required=True, help="ID OpenRouter du modèle")

    # ── reset-model ──
    p_reset = subparsers.add_parser("reset-model", help="Réinitialiser au default du niveau")
    p_reset.add_argument("--email", required=True, help="Email de l'utilisateur")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    db = SessionLocal()
    try:
        if args.command == "list":
            cmd_list(db)
        elif args.command == "tiers":
            cmd_tiers()
        elif args.command == "set-tier":
            cmd_set_tier(db, args.email, args.tier, args.model)
        elif args.command == "set-model":
            cmd_set_model(db, args.email, args.model)
        elif args.command == "reset-model":
            cmd_reset_model(db, args.email)
    finally:
        db.close()


if __name__ == "__main__":
    main()
