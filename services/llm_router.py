"""
services/llm_router.py
~~~~~~~~~~~~~~~~~~~~~~
Routeur de modèles LLM par niveau de soutien utilisateur.

Système de niveaux :
  free      → Modèles gratuits (Nemotron, Qwen-free, etc.)
  supporter → Modèles intermédiaires (Kimi, Mistral, etc.)
  donor     → Modèles premium (GPT-4o, Claude, etc.)

Chaque niveau a une liste de modèles disponibles. L'utilisateur peut
choisir dans sa liste, ou se voir attribuer un modèle par défaut.

Usage :
    from services.llm_router import get_model_for_user, list_available_models
    model = get_model_for_user(db, user_id)
    models = list_available_models("supporter")
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Charge .env
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "").strip()

from db.models import User


# ═══════════════════════════════════════════════════════════════════
# REGISTRE DES MODÈLES PAR NIVEAU
# ═══════════════════════════════════════════════════════════════════
# Format : { tier: { "default": str, "available": [str, ...] } }
#
# Les modèles sont référencés par leur ID OpenRouter (ex: "openai/gpt-4o").
# Les modèles gratuits sont marqués avec (free) en commentaire.
# ═══════════════════════════════════════════════════════════════════

LLM_REGISTRY = {
    # ── Niveau FREE (100% gratuit, pas de contribution) ──
    "free": {
        "default": os.getenv(
            "LLM_FREE_DEFAULT",
            "nepothos/nemotron-mini-4b-instruct:free",  # Nemotron 4B — gratuit, rapide
        ),
        "available": [
            "nepothos/nemotron-mini-4b-instruct:free",   # Nemotron 4B — très rapide
            "qwen/qwen2.5-7b-instruct:free",              # Qwen 2.5 7B — bon rapport qualité/vitesse
            "meta-llama/llama-3.2-3b-instruct:free",      # Llama 3.2 3B — léger
            "google/gemma-3-4b-it:free",                  # Gemma 3 4B — alternatif
        ],
        "label": "Gratuit",
        "description": "Modèles gratuits — réponse rapide, qualité standard",
    },

    # ── Niveau SUPPORTER (contribution modérée, ex: PayPal) ──
    "supporter": {
        "default": os.getenv(
            "LLM_SUPPORTER_DEFAULT",
            "moonshotai/kimi-k2:free",  # Kimi — bon modèle intermédiaire
        ),
        "available": [
            "moonshotai/kimi-k2:free",                     # Kimi K2 — excellent rapport qualité/prix
            "mistralai/mistral-large:free",                # Mistral Large — très bon
            "qwen/qwen-plus:free",                         # Qwen Plus — performant
            "deepseek/deepseek-chat:free",                 # DeepSeek Chat — alternatif solide
            "meta-llama/llama-3.3-70b-instruct:free",      # Llama 3.3 70B — puissant
        ],
        "label": "Contributeur",
        "description": "Modèle attribué aux contributeurs — meilleure qualité de coaching",
    },

    # ── Niveau DONOR (contribution généreuse) ──
    "donor": {
        "default": os.getenv(
            "LLM_DONOR_DEFAULT",
            "openai/gpt-4o",  # GPT-4o — référence
        ),
        "available": [
            "openai/gpt-4o",                                   # GPT-4o — référence actuelle
            "anthropic/claude-3.5-sonnet",                     # Claude 3.5 Sonnet — excellent
            "anthropic/claude-3-opus",                         # Claude Opus — premium
            "openai/o1",                                       # OpenAI o1 — raisonnement
            "google/gemini-1.5-pro",                           # Gemini 1.5 Pro — contexte long
            "meta-llama/llama-3.1-405b-instruct",              # Llama 405B — très puissant
        ],
        "label": "Donateur",
        "description": "Modèles premium — coaching haute précision, analyses approfondies",
    },
}

# Liste des niveaux valides
VALID_TIERS = list(LLM_REGISTRY.keys())


# ═══════════════════════════════════════════════════════════════════
# Fonctions publiques
# ═══════════════════════════════════════════════════════════════════

def get_model_for_user(db: Session, user_id: int) -> str:
    """
    Récupère le modèle LLM alloué à un utilisateur.

    Si l'utilisateur n'a pas de modèle attribué (llm_model = NULL),
    retourne le modèle par défaut de son niveau.

    Args:
        db: Session SQLAlchemy active.
        user_id: ID interne de l'utilisateur (table users).

    Returns:
        L'ID OpenRouter du modèle alloué (ex: "openai/gpt-4o").

    Raises:
        ValueError: Si l'utilisateur n'existe pas.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Si l'utilisateur a un modèle personnalisé attribué → on l'utilise
    if user.llm_model:
        return user.llm_model

    # Sinon → modèle par défaut de son niveau
    tier_config = LLM_REGISTRY.get(user.tier, LLM_REGISTRY["free"])
    return tier_config["default"]


def get_tier_for_user(db: Session, user_id: int) -> dict:
    """
    Récupère les informations de niveau d'un utilisateur.

    Returns:
        {
            "tier": "free"|"supporter"|"donor",
            "label": "Gratuit"|"Supporter"|"Donateur",
            "description": "...",
            "current_model": "openai/gpt-4o",
            "available_models": ["...", "..."],
            "can_choose": True|False  # si l'utilisateur peut changer de modèle
        }
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    tier_config = LLM_REGISTRY.get(user.tier, LLM_REGISTRY["free"])
    current_model = user.llm_model or tier_config["default"]

    return {
        "tier": user.tier,
        "label": tier_config["label"],
        "description": tier_config["description"],
        "current_model": current_model,
        "available_models": tier_config["available"],
        "can_choose": True,  # Pour l'instant tout le monde peut choisir dans sa liste
    }


def list_available_models(tier: str) -> list:
    """
    Liste les modèles disponibles pour un niveau donné.

    Args:
        tier: 'free', 'supporter', ou 'donor'.

    Returns:
        Liste des IDs de modèles OpenRouter.
    """
    tier_config = LLM_REGISTRY.get(tier, LLM_REGISTRY["free"])
    return tier_config["available"]


def set_user_model(
    db: Session,
    user_id: int,
    model_id: str,
) -> dict:
    """
    Attribue un modèle LLM à un utilisateur.

    Valide que le modèle est disponible pour le niveau de l'utilisateur.

    Args:
        db: Session SQLAlchemy active.
        user_id: ID interne de l'utilisateur.
        model_id: ID OpenRouter du modèle (ex: "openai/gpt-4o").

    Returns:
        {
            "success": True,
            "user_id": 1,
            "model": "openai/gpt-4o",
            "tier": "donor",
        }

    Raises:
        ValueError: Si le modèle n'est pas disponible pour le niveau de l'utilisateur.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    tier_config = LLM_REGISTRY.get(user.tier, LLM_REGISTRY["free"])

    # Validation : le modèle doit être dans la liste du niveau
    if model_id not in tier_config["available"]:
        available = ", ".join(tier_config["available"])
        raise ValueError(
            f"Model '{model_id}' is not available for tier '{user.tier}'. "
            f"Available models: {available}"
        )

    user.llm_model = model_id
    db.commit()

    return {
        "success": True,
        "user_id": user.id,
        "email": user.email,
        "model": model_id,
        "tier": user.tier,
    }


def set_user_tier(
    db: Session,
    user_id: int,
    tier: str,
    model_id: Optional[str] = None,
) -> dict:
    """
    Change le niveau de soutien d'un utilisateur.

    Si le nouveau niveau n'a pas le modèle actuel dans sa liste,
    le modèle est réinitialisé au default du nouveau niveau.

    Args:
        db: Session SQLAlchemy active.
        user_id: ID interne de l'utilisateur.
        tier: 'free', 'supporter', ou 'donor'.
        model_id: Optionnel — modèle à attribuer (doit être valide pour le niveau).

    Returns:
        {
            "success": True,
            "user_id": 1,
            "old_tier": "free",
            "new_tier": "supporter",
            "model": "moonshotai/kimi-k2:free",
        }
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier '{tier}'. Valid: {', '.join(VALID_TIERS)}")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    old_tier = user.tier
    tier_config = LLM_REGISTRY[tier]

    user.tier = tier

    # Si l'utilisateur a un modèle personnalisé
    if user.llm_model:
        # Le modèle actuel est-il valide pour le nouveau niveau ?
        if user.llm_model not in tier_config["available"]:
            # Non → on passe au default du nouveau niveau
            user.llm_model = tier_config["default"]
    else:
        # Pas de modèle personnalisé → default du niveau
        user.llm_model = tier_config["default"]

    # Si un modèle spécifique est demandé
    if model_id:
        if model_id in tier_config["available"]:
            user.llm_model = model_id
        else:
            raise ValueError(
                f"Model '{model_id}' not available for tier '{tier}'. "
                f"Available: {', '.join(tier_config['available'])}"
            )

    db.commit()

    return {
        "success": True,
        "user_id": user.id,
        "email": user.email,
        "old_tier": old_tier,
        "new_tier": tier,
        "model": user.llm_model,
    }


def get_all_tiers_info() -> dict:
    """
    Retourne toutes les informations sur les niveaux et modèles disponibles.

    Utile pour l'API (GET /api/llm/tiers) et l'affichage frontend.
    """
    return {
        tier: {
            "label": config["label"],
            "description": config["description"],
            "default_model": config["default"],
            "available_models": config["available"],
            "model_count": len(config["available"]),
        }
        for tier, config in LLM_REGISTRY.items()
    }
