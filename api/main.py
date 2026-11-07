"""HTTP entry point for a single eligibility check."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eligibility.purchase_lookup import lookup_purchase  # noqa: E402
from eligibility.reasoner import DEFAULT_MODEL, reason  # noqa: E402
from eligibility.rules import load_benefits  # noqa: E402
from llm_policy import load_api_key  # noqa: E402
from retriever import PolicyRetriever  # noqa: E402


app = FastAPI(title="Card Benefit Activation Engine", version="0.1")
BENEFITS_PATH = ROOT / "benefits_data.json"
CHUNKS_PATH = ROOT / "data" / "chunks.json"
API_KEY_PATH = ROOT / "api.env"


def _engine() -> tuple[list[dict[str, Any]], PolicyRetriever, str]:
    benefits = getattr(app.state, "benefits", None)
    retriever = getattr(app.state, "retriever", None)
    api_key = getattr(app.state, "api_key", None)
    if benefits is None or retriever is None or api_key is None:
        app.state.benefits = load_benefits(BENEFITS_PATH)
        app.state.retriever = PolicyRetriever(CHUNKS_PATH)
        app.state.api_key = load_api_key(API_KEY_PATH)
    return app.state.benefits, app.state.retriever, app.state.api_key


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/lookup-purchase")
def lookup(body: dict[str, Any]) -> dict[str, Any]:
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=422, detail="prompt is required")
    _benefits, retriever, _api_key = _engine()
    return lookup_purchase(
        prompt,
        retriever,
        issuer=body.get("issuer"),
        card_name=body.get("card_name"),
    )


@app.post("/check-eligibility")
def check_eligibility(transaction: dict[str, Any]) -> dict[str, Any]:
    required = {
        "issuer",
        "card_name",
        "category",
        "amount",
        "purchase_date",
        "payment_amount_on_card",
        "event",
        "evidence_available",
    }
    missing = sorted(required - transaction.keys())
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {', '.join(missing)}")
    if not isinstance(transaction.get("event"), dict):
        raise HTTPException(status_code=422, detail="event must be an object")
    benefits, retriever, api_key = _engine()
    try:
        return reason(transaction, benefits, retriever, api_key, DEFAULT_MODEL)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
