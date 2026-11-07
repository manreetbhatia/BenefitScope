"""Decide whether a purchase qualifies, using the pre-filter and the policy text."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eligibility.prefilter import prefilter  # noqa: E402
from eligibility.rules import label_transaction, load_benefits, missing_evidence  # noqa: E402
from llm_policy import GROQ_ENDPOINT, load_api_key  # noqa: E402
from retriever import PolicyRetriever  # noqa: E402


DEFAULT_MODEL = "openai/gpt-oss-20b"
EMPTY_SOURCE = {"document_title": "", "page": None, "url": ""}
_LAST_MODEL_CALL = 0.0
MODEL_CALL_GAP_SECONDS = 8.0


def gather_evidence(
    retriever: PolicyRetriever,
    transaction: dict[str, Any],
    benefit: dict[str, Any],
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """Pull the matching clause, plus the next page, which often holds exclusions."""
    query = (
        f"what does {benefit['benefit_type'].replace('_', ' ')} cover and exclude "
        f"for {transaction['issuer']} {transaction['card_name']}"
    )
    typed = retriever.search(
        query,
        top_k=top_k,
        issuer=transaction["issuer"],
        benefit_type=benefit["benefit_type"],
    )
    typed = [chunk for chunk in typed if chunk["card_name"] == transaction["card_name"]]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(chunk: dict[str, Any], score: float | None = None) -> None:
        if chunk["chunk_id"] in seen:
            return
        seen.add(chunk["chunk_id"])
        copied = dict(chunk)
        if score is not None:
            copied["score"] = score
        selected.append(copied)

    for hit in typed:
        add(hit)
        for chunk in retriever.chunks:
            if chunk["filename"] == hit["filename"] and abs(int(chunk["page"]) - int(hit["page"])) <= 1:
                add(chunk, hit.get("score", 0.0))

    if not selected:
        fallback = retriever.search(query, top_k=top_k, issuer=transaction["issuer"])
        for hit in fallback:
            if hit["card_name"] == transaction["card_name"]:
                add(hit)
    return selected[:6]


def _rule_snapshot(benefit: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "issuer",
        "card_name",
        "benefit_type",
        "coverage_window_days",
        "delay_threshold_hours",
        "max_coverage_amount",
        "max_coverage_amount_currency",
        "eligible_categories",
        "required_evidence",
        "exclusions",
        "claim_filing_deadline_days",
        "payment_requirement",
    )
    snapshot = {key: benefit[key] for key in keys}
    snapshot["source"] = {
        "document_title": benefit["source"]["document_title"],
        "url": benefit["source"]["url"],
    }
    return snapshot


def build_prompt(
    transaction: dict[str, Any],
    benefit: dict[str, Any],
    evidence: list[dict[str, Any]],
    missing: list[str],
    rule_reason: str,
) -> str:
    public_transaction = {key: value for key, value in transaction.items() if key != "ground_truth"}
    excerpts = []
    for index, chunk in enumerate(evidence[:3], start=1):
        text = " ".join(str(chunk.get("text") or "").split())[:600]
        excerpts.append(
            "EXCERPT "
            + str(index)
            + ": "
            + json.dumps(
                {
                    "document_title": chunk.get("document_title"),
                    "page": chunk.get("page"),
                    "url": chunk.get("source_url"),
                    "benefit_type": chunk.get("benefit_type"),
                    "text": text,
                }
            )
        )
    excerpt_text = "\n\n".join(excerpts) if excerpts else "No policy excerpt was retrieved."
    return f"""You are deciding a card-benefit claim for an ordinary cardholder.
Use only the structured benefit rule and the policy excerpts. Do not invent coverage amounts, day limits, exclusions, or required documents.
If a number is not written in the rule or in an excerpt, do not state it.
The structured rule is the authority for this card's numbers. A retrieved excerpt may add exclusions.
If required documents are missing, the answer is not eligible.
MISSING DOCUMENTS is the complete list. If it is empty, do not require another document.
photos of damage apply only to a damage event. A police report applies only to a theft event.
If the excerpts do not discuss this benefit and do not contradict the structured rule, follow the structured rule.
If an excerpt clearly contradicts the structured rule for this purchase, follow the excerpt and quote that sentence.
Return valid JSON only with exactly these keys:
eligible (boolean), benefit_type (string), confidence (number from 0 to 1),
cited_clause (string, a short quote), cited_source (object with document_title, page, url),
reason (string in everyday words).

STRUCTURED RULE:
{json.dumps(_rule_snapshot(benefit))}

RULE CHECK ALREADY COMPLETED:
{rule_reason}

MISSING DOCUMENTS:
{json.dumps(missing)}

PURCHASE:
{json.dumps(public_transaction)}

POLICY EXCERPTS:
{excerpt_text}
"""


def parse_model_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def ask_model(prompt: str, api_key: str, model: str) -> dict[str, Any]:
    global _LAST_MODEL_CALL
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return only valid JSON. Do not invent policy terms."},
            {"role": "user", "content": prompt},
        ],
    }
    last_error = "Groq API request failed"
    for attempt in range(4):
        gap = MODEL_CALL_GAP_SECONDS - (time.time() - _LAST_MODEL_CALL)
        if _LAST_MODEL_CALL and gap > 0:
            time.sleep(gap)
        request = Request(
            GROQ_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "card-benefit-activation-engine/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
            _LAST_MODEL_CALL = time.time()
            return parse_model_json(body["choices"][0]["message"]["content"])
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            _LAST_MODEL_CALL = time.time()
            last_error = f"Groq API request failed ({error.code})"
            if error.code == 429 and attempt < 3:
                match = re.search(r"try again in ([0-9.]+)s", detail)
                time.sleep(float(match.group(1)) + 1 if match else 20)
                continue
            raise RuntimeError(last_error) from error
        except URLError as error:
            raise RuntimeError("Could not reach the Groq API") from error
    raise RuntimeError(last_error)


def _source_from_chunk(chunk: dict[str, Any] | None, benefit: dict[str, Any]) -> dict[str, Any]:
    if chunk:
        return {
            "document_title": chunk.get("document_title") or "",
            "page": chunk.get("page"),
            "url": chunk.get("source_url") or "",
        }
    source = benefit.get("source") or {}
    return {
        "document_title": source.get("document_title") or "",
        "page": None,
        "url": source.get("url") or "",
    }


def _normalize(
    transaction: dict[str, Any],
    benefit: dict[str, Any],
    raw: dict[str, Any],
    evidence: list[dict[str, Any]],
    missing: list[str],
) -> dict[str, Any]:
    cited_source = raw.get("cited_source") if isinstance(raw.get("cited_source"), dict) else {}
    source = {
        "document_title": cited_source.get("document_title") or "",
        "page": cited_source.get("page"),
        "url": cited_source.get("url") or cited_source.get("source_url") or "",
    }
    if not source["document_title"]:
        source = _source_from_chunk(evidence[0] if evidence else None, benefit)
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    cited_clause = str(raw.get("cited_clause") or "").strip()
    if not cited_clause and evidence:
        cited_clause = " ".join(str(evidence[0].get("text") or "").split())[:500]
    eligible = bool(raw.get("eligible"))
    reason = str(raw.get("reason") or "").strip()
    if missing:
        eligible = False
        readable = ", ".join(item.replace("_", " ") for item in missing)
        reason = f"This purchase is missing required documents: {readable}."
    return {
        "transaction_id": transaction.get("transaction_id"),
        "eligible": eligible,
        "benefit_type": benefit["benefit_type"],
        "confidence": round(confidence, 2),
        "cited_clause": cited_clause,
        "cited_source": source,
        "missing_evidence": missing,
        "reason": reason,
        "decision_source": "model",
    }


def _from_rule(
    transaction: dict[str, Any],
    benefit: dict[str, Any],
    evidence: list[dict[str, Any]],
    missing: list[str],
    rule: dict[str, Any],
    note: str,
) -> dict[str, Any]:
    clause = ""
    if evidence:
        clause = " ".join(str(evidence[0].get("text") or "").split())[:500]
    elif rule.get("reason"):
        clause = rule["reason"]
    return {
        "transaction_id": transaction.get("transaction_id"),
        "eligible": bool(rule["eligible"]) and not missing,
        "benefit_type": benefit["benefit_type"],
        "confidence": 0.55,
        "cited_clause": clause,
        "cited_source": _source_from_chunk(evidence[0] if evidence else None, benefit),
        "missing_evidence": missing,
        "reason": note or rule.get("reason") or "",
        "decision_source": "benefit_rule",
    }


def reject(transaction: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "transaction_id": transaction.get("transaction_id"),
        "eligible": False,
        "benefit_type": None,
        "confidence": 1.0,
        "cited_clause": "",
        "cited_source": dict(EMPTY_SOURCE),
        "missing_evidence": [],
        "reason": reason,
        "decision_source": "hard_check",
    }


def reason(
    transaction: dict[str, Any],
    benefits: list[dict[str, Any]],
    retriever: PolicyRetriever,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Return an eligibility result for one purchase.

    Purchases that fail the hard checks never call the model. Purchases that
    still look possible are sent with the matching policy text. Missing
    documents force a not-eligible result so the model cannot waive them.
    """
    candidates = prefilter(transaction, benefits)
    if not candidates:
        ruled = label_transaction(transaction, benefits)
        return reject(transaction, ruled["reason"])

    judgments: list[dict[str, Any]] = []
    for benefit in candidates:
        evidence = gather_evidence(retriever, transaction, benefit)
        missing = missing_evidence(transaction, benefit)
        rule = label_transaction(transaction, benefits)
        prompt = build_prompt(transaction, benefit, evidence, missing, rule["reason"])
        try:
            raw = ask_model(prompt, api_key, model)
            judgment = _normalize(transaction, benefit, raw, evidence, missing)
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as error:
            judgment = _from_rule(
                transaction,
                benefit,
                evidence,
                missing,
                rule,
                f"The policy model could not be read ({error}). The structured benefit rule was used instead.",
            )
        if not missing and rule["eligible"] and not judgment["eligible"]:
            text = judgment["reason"].lower()
            if "missing" in text and any(token in text for token in ("photo", "police", "receipt")):
                judgment["eligible"] = True
                judgment["decision_source"] = "benefit_rule"
                judgment["checklist_override"] = True
                judgment["reason"] = (
                    rule["reason"]
                    + " The model asked for a document this event does not require, so the benefit checklist was kept."
                )
        judgments.append(judgment)

    approved = [item for item in judgments if item["eligible"]]
    pool = approved or judgments
    return max(pool, key=lambda item: item["confidence"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--transactions", type=Path, default=ROOT / "data" / "transactions.json")
    parser.add_argument("--benefits", type=Path, default=ROOT / "benefits_data.json")
    parser.add_argument("--chunks", type=Path, default=ROOT / "data" / "chunks.json")
    parser.add_argument("--api-file", type=Path, default=ROOT / "api.env")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    transactions = json.loads(args.transactions.read_text(encoding="utf-8"))
    transaction = next(item for item in transactions if item["transaction_id"] == args.transaction_id)
    result = reason(
        transaction,
        load_benefits(args.benefits),
        PolicyRetriever(args.chunks),
        load_api_key(args.api_file),
        args.model,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
