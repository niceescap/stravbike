"""Authenticated OpenWebUI handler for the multi-user application."""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator

import httpx
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

logger = logging.getLogger("stravbike.llm_handler")

OPENWEBUI_BASE_URL = os.getenv("OPENWEBUI_BASE_URL", "").rstrip("/")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "")
OPENWEBUI_TOOL_IDS = [
    value.strip()
    for value in os.getenv("OPENWEBUI_TOOL_IDS", "").split(",")
    if value.strip()
]
MAX_TOOL_ITERATIONS = 5


class LLMConfigurationError(RuntimeError):
    """The OpenWebUI configuration is incomplete."""


def validate_configuration() -> None:
    missing = []
    if not OPENWEBUI_BASE_URL:
        missing.append("OPENWEBUI_BASE_URL")
    if not OPENWEBUI_API_KEY:
        missing.append("OPENWEBUI_API_KEY")
    if not OPENWEBUI_MODEL:
        missing.append("OPENWEBUI_MODEL")
    if missing:
        raise LLMConfigurationError(
            "Configuration OpenWebUI incomplète: " + ", ".join(missing)
        )


def build_user_context(user, athlete) -> str:
    user_name = " ".join(
        part for part in (user.firstname, user.lastname) if part
    ).strip() or "Utilisateur"
    athlete_name = (
        " ".join(part for part in (athlete.firstname, athlete.lastname) if part).strip()
        if athlete else "Aucun athlète associé"
    )
    return (
        "Tu es le coach IA de Stravbike.\n"
        "Contexte authentifié fourni par le serveur :\n"
        f"- Utilisateur : {user_name}\n"
        f"- Email utilisateur : {user.email}\n"
        f"- User ID interne : {user.id}\n"
        f"- Athlète courant : {athlete_name}\n"
        f"- Athlete ID interne : {athlete.id if athlete else 'none'}\n"
        f"- Strava ID : {athlete.strava_id if athlete else 'none'}\n"
        "Réponds à cet utilisateur uniquement. Ne mélange jamais ses données "
        "avec celles d'un autre utilisateur."
    )


def _model_for_user(user_model: str | None) -> str:
    return (user_model or OPENWEBUI_MODEL).strip()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _json_value(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (int, float)):
        return float(value)
    return value


async def execute_tool(name: str, arguments: dict, user, athlete, db: Session) -> str:
    """Execute read tools directly against the authenticated user's DB scope."""
    from db.models import Activity, Competition, PlannedSession

    if not athlete:
        return "Erreur: aucun athlète n'est associé à cet utilisateur."

    if name == "get_athlete_profile":
        return json.dumps({
            "user": {"id": user.id, "email": user.email},
            "athlete": {
                "id": athlete.id,
                "strava_id": athlete.strava_id,
                "firstname": athlete.firstname,
                "lastname": athlete.lastname,
                "ftp_watts": _json_value(athlete.ftp_watts),
                "weight_kg": _json_value(athlete.weight_kg),
                "power_zones": athlete.power_zones,
                "heart_rate_zones": athlete.heart_rate_zones,
                "ytd_distance_km": _json_value(athlete.ytd_distance_km),
                "ytd_elevation_m": athlete.ytd_elevation_m,
                "ytd_time_hours": _json_value(athlete.ytd_time_hours),
            },
        }, ensure_ascii=False)

    if name in {"get_activity_detail", "get_activity"}:
        activity_id = arguments.get("activity_id")
        activity = db.query(Activity).filter(
            Activity.id == int(activity_id), Activity.athlete_id == athlete.id
        ).first()
        if not activity:
            return "Erreur: activité introuvable pour cet athlète."
        data = {
            column.name: _json_value(getattr(activity, column.name))
            for column in Activity.__table__.columns
        }
        return json.dumps(data, ensure_ascii=False)

    if name in {"get_week_calendar", "get_calendar"}:
        raw_start = arguments.get("start_date") or arguments.get("week")
        try:
            start = datetime.strptime(raw_start, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return "Erreur: la date doit être au format YYYY-MM-DD."
        end = start + timedelta(days=6)
        activities = db.query(Activity).filter(
            Activity.athlete_id == athlete.id,
            Activity.start_date_local >= start,
            Activity.start_date_local <= end,
        ).order_by(Activity.start_date_local).all()
        sessions = db.query(PlannedSession).filter(
            PlannedSession.athlete_id == athlete.id,
            PlannedSession.session_date >= start,
            PlannedSession.session_date <= end,
        ).order_by(PlannedSession.session_date).all()
        return json.dumps({
            "start_date": str(start),
            "end_date": str(end),
            "activities": [
                {column.name: _json_value(getattr(item, column.name))
                 for column in Activity.__table__.columns}
                for item in activities
            ],
            "planned_sessions": [
                {column.name: _json_value(getattr(item, column.name))
                 for column in PlannedSession.__table__.columns}
                for item in sessions
            ],
        }, ensure_ascii=False)

    if name in {"get_competitions", "get_all_competitions"}:
        competitions = db.query(Competition).filter(
            Competition.athlete_id == athlete.id
        ).order_by(Competition.competition_date).all()
        return json.dumps([
            {column.name: _json_value(getattr(item, column.name))
             for column in Competition.__table__.columns}
            for item in competitions
        ], ensure_ascii=False)

    if name in {"get_planned_sessions", "get_sessions"}:
        raw_week = arguments.get("week") or arguments.get("start_date")
        try:
            start = datetime.strptime(raw_week, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return "Erreur: la semaine doit être au format YYYY-MM-DD."
        end = start + timedelta(days=6)
        sessions = db.query(PlannedSession).filter(
            PlannedSession.athlete_id == athlete.id,
            PlannedSession.session_date >= start,
            PlannedSession.session_date <= end,
        ).all()
        return json.dumps([
            {column.name: _json_value(getattr(item, column.name))
             for column in PlannedSession.__table__.columns}
            for item in sessions
        ], ensure_ascii=False)

    return f"Erreur: outil '{name}' non reconnu par le handler multi-utilisateur."


async def stream_chat(
    messages: list[dict], user, athlete, db: Session
) -> AsyncIterator[str]:
    """Forward a conversation and execute returned tool calls in user scope."""
    try:
        validate_configuration()
    except LLMConfigurationError as exc:
        yield _sse({"error": str(exc)})
        yield "data: [DONE]\n\n"
        return

    clean_messages = [
        message for message in messages
        if isinstance(message, dict) and message.get("role") != "system"
    ]
    if not clean_messages:
        yield _sse({"error": "Aucun message fourni"})
        yield "data: [DONE]\n\n"
        return

    conversation = [
        {"role": "system", "content": build_user_context(user, athlete)},
        *clean_messages,
    ]
    headers = {
        "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    endpoint = f"{OPENWEBUI_BASE_URL}/api/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
                payload = {
                    "model": _model_for_user(getattr(user, "llm_model", None)),
                    "stream": True,
                    "messages": conversation,
                }
                if OPENWEBUI_TOOL_IDS:
                    payload["tool_ids"] = OPENWEBUI_TOOL_IDS
                logger.warning(
                    "OpenWebUI request: iteration=%s model=%s user_id=%s athlete_id=%s tools=%s endpoint=%s",
                    iteration, payload["model"], user.id, getattr(athlete, "id", None),
                    OPENWEBUI_TOOL_IDS, endpoint,
                )

                accumulated_content = ""
                accumulated_reasoning = ""
                tool_calls = {}
                finish_reason = None

                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    logger.warning(
                        "OpenWebUI response: HTTP %s content-type=%s",
                        response.status_code, response.headers.get("content-type", "?"),
                    )
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", "replace")
                        logger.error("OpenWebUI HTTP %s: %s", response.status_code, body[:500])
                        yield _sse({"error": f"OpenWebUI HTTP {response.status_code}: {body[:300]}"})
                        return

                    async for line in response.aiter_lines():
                        raw = line.strip()
                        if not raw:
                            continue
                        data = raw[5:].strip() if raw.startswith("data:") else raw
                        if data == "[DONE]":
                            break
                        if not data.startswith("{"):
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            logger.warning("OpenWebUI non-JSON event: %s", data[:200])
                            continue

                        choices = chunk.get("choices") or []
                        choice = choices[0] if choices else {}
                        delta = choice.get("delta") or {}
                        message = choice.get("message") or {}
                        finish_reason = choice.get("finish_reason") or finish_reason

                        content = (
                            delta.get("content") or message.get("content")
                            or choice.get("text") or chunk.get("content")
                        )
                        if isinstance(content, list):
                            content = "".join(
                                item.get("text", "") if isinstance(item, dict) else str(item)
                                for item in content
                            )
                        if content:
                            accumulated_content += content
                            yield _sse({"content": content})

                        reasoning = (
                            delta.get("reasoning") or delta.get("reasoning_content")
                            or message.get("reasoning") or message.get("reasoning_content")
                            or chunk.get("reasoning") or chunk.get("reasoning_content")
                        )
                        if reasoning:
                            accumulated_reasoning += reasoning
                            yield _sse({"reasoning": reasoning})

                        for tc in (delta.get("tool_calls") or message.get("tool_calls") or []):
                            index = tc.get("index", 0)
                            item = tool_calls.setdefault(index, {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            })
                            if tc.get("id"):
                                item["id"] = tc["id"]
                            function = tc.get("function") or {}
                            if function.get("name"):
                                item["function"]["name"] = function["name"]
                            item["function"]["arguments"] += function.get("arguments", "")
                            yield _sse({"tool_status": "Le coach consulte les données Strava…"})

                ordered_tools = [tool_calls[index] for index in sorted(tool_calls)]
                if not ordered_tools or finish_reason != "tool_calls":
                    break

                assistant_message = {
                    "role": "assistant",
                    "content": accumulated_content,
                    "tool_calls": ordered_tools,
                }
                if accumulated_reasoning:
                    assistant_message["reasoning"] = accumulated_reasoning
                conversation.append(assistant_message)

                for tool_call in ordered_tools:
                    function = tool_call["function"]
                    try:
                        arguments = json.loads(function["arguments"] or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    name = function.get("name", "")
                    logger.warning("Executing tool: %s(%s)", name, arguments)
                    result = await execute_tool(name, arguments, user, athlete, db)
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": result,
                    })
            else:
                yield _sse({"error": "Limite d'itérations tool_call atteinte"})

    except httpx.RequestError as exc:
        logger.exception("OpenWebUI unavailable")
        yield _sse({"error": f"OpenWebUI inaccessible: {exc}"})
    except Exception as exc:
        logger.exception("Unexpected LLM handler error")
        yield _sse({"error": f"Erreur du handler LLM: {exc}"})
    finally:
        yield "data: [DONE]\n\n"
