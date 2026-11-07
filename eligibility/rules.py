"""Deterministic checks shared by the dataset labels and the pre-filter.

Every eligible/not-eligible label is computed from benefits_data.json.
The pre-filter stops at hard facts (card, event, category, dates, payment).
The ground-truth label also requires the documents that benefit asks for.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


EVENT_TO_BENEFIT = {
    "theft": "purchase_protection",
    "damage": "purchase_protection",
    "store_return_denied": "return_protection",
    "flight_delay": "trip_delay_insurance",
    "none": None,
}


def load_benefits(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return list(payload["benefits"])
    return list(payload)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def days_after_purchase(transaction: dict[str, Any]) -> int | None:
    event_date = parse_date(transaction["event"].get("event_date"))
    purchase_date = parse_date(transaction.get("purchase_date"))
    if event_date is None or purchase_date is None:
        return None
    return (event_date - purchase_date).days


def payment_ok(transaction: dict[str, Any], benefit: dict[str, Any]) -> bool:
    paid = float(transaction["payment_amount_on_card"])
    amount = float(transaction["amount"])
    if paid <= 0:
        return False
    if benefit["payment_requirement"] == "full_amount_on_card":
        return paid + 1e-6 >= amount
    return True


def window_status(transaction: dict[str, Any], benefit: dict[str, Any]) -> tuple[bool, str]:
    """Say whether the event falls inside this benefit's time or delay rule."""
    event = transaction["event"]
    if benefit["benefit_type"] == "trip_delay_insurance":
        delay = event.get("delay_hours")
        threshold = benefit["delay_threshold_hours"]
        if delay is None or threshold is None:
            return False, "no delay length was reported"
        if delay >= threshold:
            return True, f"the delay of {delay} hours meets the {threshold}-hour minimum"
        return False, f"the delay of {delay} hours is below the {threshold}-hour minimum"

    elapsed = days_after_purchase(transaction)
    window = benefit["coverage_window_days"]
    if elapsed is None or window is None:
        return False, "there is no event date to compare with the coverage window"
    if elapsed < 0:
        return False, "the event date is before the purchase date"
    if elapsed <= window:
        return True, f"the event is on day {elapsed} of the {window}-day coverage window"
    return False, f"the event is on day {elapsed}, which is past the {window}-day coverage window"


def applicable_evidence(benefit: dict[str, Any], event_type: str) -> list[str]:
    """Documents this event actually needs. Conditional items apply only then."""
    required: list[str] = []
    for item in benefit["required_evidence"]:
        if item == "police_report_if_theft":
            if event_type == "theft":
                required.append(item)
        elif item == "photos_if_damage":
            if event_type == "damage":
                required.append(item)
        elif str(item).endswith("_if_applicable"):
            continue
        else:
            required.append(item)
    return required


def missing_evidence(transaction: dict[str, Any], benefit: dict[str, Any]) -> list[str]:
    have = set(transaction.get("evidence_available") or [])
    event_type = transaction["event"]["event_type"]
    return [item for item in applicable_evidence(benefit, event_type) if item not in have]


def find_benefit(
    transaction: dict[str, Any],
    benefits: list[dict[str, Any]],
    benefit_type: str,
) -> dict[str, Any] | None:
    for benefit in benefits:
        if (
            benefit["issuer"] == transaction["issuer"]
            and benefit["card_name"] == transaction["card_name"]
            and benefit["benefit_type"] == benefit_type
        ):
            return benefit
    return None


def hard_check_failure(transaction: dict[str, Any], benefit: dict[str, Any]) -> str | None:
    """Return why this benefit cannot apply, or None if the hard checks pass.

    An amount above the coverage cap is allowed through: the card can still
    reimburse part of the purchase.
    """
    if benefit["issuer"] != transaction["issuer"] or benefit["card_name"] != transaction["card_name"]:
        return "this benefit belongs to a different card"
    expected = EVENT_TO_BENEFIT.get(transaction["event"]["event_type"])
    if expected != benefit["benefit_type"]:
        return "the event does not match this benefit"
    category = transaction["category"]
    if category not in benefit["eligible_categories"]:
        return f"category {category} is not covered"
    if category in benefit.get("exclusions", []):
        return f"category {category} is excluded"
    if float(transaction["amount"]) <= 0:
        return "the purchase amount is not positive"
    inside_window, window_reason = window_status(transaction, benefit)
    if not inside_window:
        return window_reason
    if not payment_ok(transaction, benefit):
        return f"the amount charged to the card does not meet {benefit['payment_requirement']}"
    return None


def label_transaction(transaction: dict[str, Any], benefits: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the ground_truth object for one synthetic transaction."""
    event_type = transaction["event"]["event_type"]
    benefit_type = EVENT_TO_BENEFIT.get(event_type)
    if not benefit_type:
        return {
            "eligible": False,
            "benefit_type": None,
            "reason": "No damage, theft, denied return, or flight delay is attached to this purchase.",
        }

    benefit = find_benefit(transaction, benefits, benefit_type)
    if benefit is None:
        pretty = benefit_type.replace("_", " ")
        return {
            "eligible": False,
            "benefit_type": None,
            "reason": f"{transaction['issuer']} {transaction['card_name']} does not offer {pretty}.",
        }

    failure = hard_check_failure(transaction, benefit)
    missing = missing_evidence(transaction, benefit)
    if failure or missing:
        parts: list[str] = []
        if failure:
            parts.append(failure)
        if missing:
            parts.append("missing evidence: " + ", ".join(missing))
        return {"eligible": False, "benefit_type": benefit_type, "reason": "; ".join(parts)}

    _ok, message = window_status(transaction, benefit)
    reason = message[0].upper() + message[1:] + "."
    if float(transaction["amount"]) > float(benefit["max_coverage_amount"]):
        cap = benefit["max_coverage_amount"]
        reason += (
            f" The purchase is above the ${cap:.0f} cap, so any reimbursement would be partial."
        )
    return {"eligible": True, "benefit_type": benefit_type, "reason": reason}
