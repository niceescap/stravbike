import os
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from db.models import LLMAnalysis
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

def call_openrouter(prompt: str, system_msg: str = "Tu es un coach de cyclisme.", max_tokens: int = 1000) -> dict:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens
    }
    start = time.time()
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
    latency = int((time.time() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()["choices"][0]["message"]["content"]
    tokens_input = resp.json().get("usage", {}).get("prompt_tokens")
    tokens_output = resp.json().get("usage", {}).get("completion_tokens")
    return {
        "response": data,
        "model": MODEL,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_ms": latency
    }

def get_cached_or_call(db: Session, analysis_type: str, entity_type: str, entity_id: int, input_payload: dict, prompt: str, max_age_hours: int = 24) -> str:
    # Cherche dans le cache
    cache_entry = db.query(LLMAnalysis).filter(
        LLMAnalysis.analysis_type == analysis_type,
        LLMAnalysis.entity_type == entity_type,
        LLMAnalysis.entity_id == entity_id,
        LLMAnalysis.expires_at > datetime.utcnow()
    ).first()
    if cache_entry:
        return cache_entry.cached_response

    result = call_openrouter(prompt)
    # Sauvegarder
    entry = LLMAnalysis(
        analysis_type=analysis_type,
        entity_type=entity_type,
        entity_id=entity_id,
        input_payload=input_payload,
        prompt_text=prompt,
        cached_response=result["response"],
        model_used=result["model"],
        tokens_input=result.get("tokens_input"),
        tokens_output=result.get("tokens_output"),
        latency_ms=result.get("latency_ms"),
        expires_at=datetime.utcnow() + timedelta(hours=max_age_hours)
    )
    db.add(entry)
    db.commit()
    return result["response"]
