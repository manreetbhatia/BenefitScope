"""Build a labeled synthetic transaction set from benefits_data.json.

The eligible/not-eligible flag is not hand-waved. It is computed with the
same rules the pre-filter uses, plus the document checklist, so every label
can be traced back to a real benefit record.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eligibility.rules import applicable_evidence, label_transaction, load_benefits  # noqa: E402


TARGET_COUNT = 400
PURCHASE_ANCHOR = date(2026, 6, 1)

MERCHANTS = {
    "electronics": ["Best Buy", "Apple Store", "B&H Photo"],
    "appliances": ["Home Depot", "Lowe's"],
    "clothing": ["Nordstrom", "Uniqlo", "Macy's"],
    "jewelry": ["Kay Jewelers", "Tiffany & Co."],
    "household_goods": ["Target", "IKEA", "Bed Bath & Beyond"],
    "common_carrier_travel": ["United Airlines", "Delta Air Lines", "Amtrak"],
    "groceries": ["Whole Foods", "Trader Joe's"],
    "motor_vehicles": ["City Auto Sales"],
    "boats_and_aircraft": ["Harbor Boat Works"],
    "animals": ["City Pet Shop"],
    "plants": ["Green Thumb Nursery"],
    "antiques": ["Old Town Antiques"],
    "used_or_pre_owned_items": ["Second Chance Resale"],
    "computer_software": ["Software Hut"],
    "perishable_items": ["Fresh Market"],
    "consumable_items": ["Corner Pharmacy"],
    "items_sold_as_is_or_final_sale": ["Outlet Final Sale"],
    "real_estate": ["Metro Realty"],
    "perishable_or_consumable_items": ["Daily Grocer"],
}

EVENT_FOR_BENEFIT = {
    "purchase_protection": "theft",
    "return_protection": "store_return_denied",
    "trip_delay_insurance": "flight_delay",
}


def merchant_for(category: str, rng: random.Random) -> str:
    choices = MERCHANTS.get(category) or ["General Merchant"]
    return rng.choice(choices)


def build_transaction(
    *,
    issuer: str,
    card_name: str,
    merchant: str,
    category: str,
    amount: float,
    purchase_date: date,
    payment_amount_on_card: float,
    event_type: str,
    event_date: date | None,
    delay_hours: int | None,
    evidence_available: list[str],
) -> dict[str, Any]:
    return {
        "issuer": issuer,
        "card_name": card_name,
        "merchant": merchant,
        "category": category,
        "amount": round(float(amount), 2),
        "currency": "USD",
        "purchase_date": purchase_date.isoformat(),
        "payment_amount_on_card": round(float(payment_amount_on_card), 2),
        "event": {
            "event_type": event_type,
            "event_date": event_date.isoformat() if event_date else None,
            "delay_hours": delay_hours,
        },
        "evidence_available": list(evidence_available),
    }


def complete_evidence(benefit: dict[str, Any], event_type: str) -> list[str]:
    return applicable_evidence(benefit, event_type)


def dropped_evidence(benefit: dict[str, Any], event_type: str) -> list[str]:
    required = complete_evidence(benefit, event_type)
    if not required:
        return []
    return required[1:]


def add_case(
    cases: list[dict[str, Any]],
    benefits: list[dict[str, Any]],
    draft: dict[str, Any],
) -> None:
    draft["ground_truth"] = label_transaction(draft, benefits)
    cases.append(draft)


def fixed_cases(benefits: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    """Hand-shaped rows for boundaries: last covered day, one day late, delay cutoffs."""
    cases: list[dict[str, Any]] = []
    for index, benefit in enumerate(benefits):
        issuer = benefit["issuer"]
        card_name = benefit["card_name"]
        benefit_type = benefit["benefit_type"]
        purchase_date = PURCHASE_ANCHOR + timedelta(days=index)
        covered_category = benefit["eligible_categories"][0]
        under_cap = min(220.0, float(benefit["max_coverage_amount"]) - 20)
        over_cap = float(benefit["max_coverage_amount"]) + 75
        event_type = EVENT_FOR_BENEFIT[benefit_type]

        def emit(
            *,
            category: str,
            amount: float,
            payment: float,
            event: str,
            offset_days: int | None,
            delay_hours: int | None,
            evidence: list[str],
        ) -> None:
            event_date = None if offset_days is None else purchase_date + timedelta(days=offset_days)
            add_case(
                cases,
                benefits,
                build_transaction(
                    issuer=issuer,
                    card_name=card_name,
                    merchant=merchant_for(category, rng),
                    category=category,
                    amount=amount,
                    purchase_date=purchase_date,
                    payment_amount_on_card=payment,
                    event_type=event,
                    event_date=event_date,
                    delay_hours=delay_hours,
                    evidence_available=evidence,
                ),
            )

        if benefit_type == "trip_delay_insurance":
            threshold = int(benefit["delay_threshold_hours"])
            evidence = complete_evidence(benefit, "flight_delay")
            emit(
                category=covered_category,
                amount=under_cap,
                payment=under_cap,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold,
                evidence=evidence,
            )
            emit(
                category=covered_category,
                amount=under_cap,
                payment=under_cap,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold - 1,
                evidence=evidence,
            )
            emit(
                category=covered_category,
                amount=under_cap,
                payment=under_cap,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold + 1,
                evidence=evidence,
            )
            emit(
                category=covered_category,
                amount=over_cap,
                payment=over_cap,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold + 4,
                evidence=evidence,
            )
            emit(
                category="electronics",
                amount=under_cap,
                payment=under_cap,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold + 3,
                evidence=evidence,
            )
            emit(
                category=covered_category,
                amount=under_cap,
                payment=under_cap,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold + 2,
                evidence=dropped_evidence(benefit, "flight_delay"),
            )
            emit(
                category=covered_category,
                amount=under_cap,
                payment=0,
                event="flight_delay",
                offset_days=0,
                delay_hours=threshold + 2,
                evidence=evidence,
            )
            emit(
                category=covered_category,
                amount=under_cap,
                payment=under_cap,
                event="none",
                offset_days=None,
                delay_hours=None,
                evidence=["original_receipt"],
            )
            if benefit["payment_requirement"] == "full_amount_on_card":
                emit(
                    category=covered_category,
                    amount=under_cap,
                    payment=round(under_cap / 2, 2),
                    event="flight_delay",
                    offset_days=0,
                    delay_hours=threshold + 2,
                    evidence=evidence,
                )
            continue

        window = int(benefit["coverage_window_days"])
        evidence = complete_evidence(benefit, event_type)
        for offset in (window // 2, window - 1, window):
            emit(
                category=covered_category,
                amount=under_cap,
                payment=under_cap,
                event=event_type,
                offset_days=offset,
                delay_hours=None,
                evidence=evidence,
            )
        emit(
            category=covered_category,
            amount=over_cap,
            payment=over_cap,
            event=event_type,
            offset_days=min(10, window),
            delay_hours=None,
            evidence=evidence,
        )
        emit(
            category=covered_category,
            amount=under_cap,
            payment=under_cap,
            event=event_type,
            offset_days=window + 1,
            delay_hours=None,
            evidence=evidence,
        )
        emit(
            category="groceries",
            amount=under_cap,
            payment=under_cap,
            event=event_type,
            offset_days=10,
            delay_hours=None,
            evidence=evidence,
        )
        excluded = benefit["exclusions"][0]
        emit(
            category=excluded,
            amount=under_cap,
            payment=under_cap,
            event=event_type,
            offset_days=10,
            delay_hours=None,
            evidence=evidence,
        )
        emit(
            category=covered_category,
            amount=under_cap,
            payment=under_cap,
            event=event_type,
            offset_days=10,
            delay_hours=None,
            evidence=dropped_evidence(benefit, event_type),
        )
        emit(
            category=covered_category,
            amount=under_cap,
            payment=0,
            event=event_type,
            offset_days=10,
            delay_hours=None,
            evidence=evidence,
        )
        emit(
            category=covered_category,
            amount=under_cap,
            payment=under_cap,
            event="none",
            offset_days=None,
            delay_hours=None,
            evidence=["original_receipt"],
        )
        if benefit_type == "purchase_protection":
            damage_evidence = complete_evidence(benefit, "damage")
            emit(
                category=benefit["eligible_categories"][min(1, len(benefit["eligible_categories"]) - 1)],
                amount=under_cap,
                payment=under_cap,
                event="damage",
                offset_days=min(15, window),
                delay_hours=None,
                evidence=damage_evidence,
            )
        if benefit["payment_requirement"] == "full_amount_on_card":
            emit(
                category=covered_category,
                amount=under_cap,
                payment=round(under_cap / 2, 2),
                event=event_type,
                offset_days=10,
                delay_hours=None,
                evidence=evidence,
            )

    citi_purchase = next(
        benefit
        for benefit in benefits
        if benefit["issuer"] == "Citi" and benefit["benefit_type"] == "purchase_protection"
    )
    add_case(
        cases,
        benefits,
        build_transaction(
            issuer="Citi",
            card_name="Strata Premier",
            merchant="Best Buy",
            category="electronics",
            amount=250,
            purchase_date=date(2026, 7, 1),
            payment_amount_on_card=250,
            event_type="store_return_denied",
            event_date=date(2026, 7, 20),
            delay_hours=None,
            evidence_available=complete_evidence(citi_purchase, "theft"),
        ),
    )
    return cases


def random_case(
    rng: random.Random,
    benefits: list[dict[str, Any]],
    want_eligible: bool,
) -> dict[str, Any]:
    cards = sorted({(benefit["issuer"], benefit["card_name"]) for benefit in benefits})
    for _attempt in range(40):
        issuer, card_name = rng.choice(cards)
        card_benefits = [
            benefit
            for benefit in benefits
            if benefit["issuer"] == issuer and benefit["card_name"] == card_name
        ]
        benefit = rng.choice(card_benefits)
        purchase_date = date(2026, 3, 1) + timedelta(days=rng.randint(0, 120))
        mode = rng.choice(["clean", "late", "wrong_category", "missing_docs", "unpaid", "no_event", "partial_pay"])
        if want_eligible:
            mode = "clean"

        if mode == "no_event":
            category = rng.choice(benefit["eligible_categories"])
            amount = round(rng.uniform(40, 180), 2)
            draft = build_transaction(
                issuer=issuer,
                card_name=card_name,
                merchant=merchant_for(category, rng),
                category=category,
                amount=amount,
                purchase_date=purchase_date,
                payment_amount_on_card=amount,
                event_type="none",
                event_date=None,
                delay_hours=None,
                evidence_available=["original_receipt"],
            )
        else:
            event_type = EVENT_FOR_BENEFIT[benefit["benefit_type"]]
            if mode == "wrong_category":
                category = "groceries" if benefit["benefit_type"] != "trip_delay_insurance" else "electronics"
            else:
                category = rng.choice(benefit["eligible_categories"])
            cap = float(benefit["max_coverage_amount"])
            amount = round(rng.uniform(40, min(250, cap - 1)), 2)
            if benefit["benefit_type"] == "trip_delay_insurance":
                threshold = int(benefit["delay_threshold_hours"])
                delay_hours = threshold + rng.randint(0, 10)
                if mode == "late":
                    delay_hours = max(0, threshold - rng.randint(1, 4))
                offset = 0
            else:
                delay_hours = None
                window = int(benefit["coverage_window_days"])
                offset = rng.randint(0, window)
                if mode == "late":
                    offset = window + rng.randint(1, 15)
            evidence = complete_evidence(benefit, event_type)
            if mode == "missing_docs" and evidence:
                evidence = evidence[:-1]
            payment = amount
            if mode == "unpaid":
                payment = 0
            elif mode == "partial_pay":
                payment = round(amount / 2, 2)
            draft = build_transaction(
                issuer=issuer,
                card_name=card_name,
                merchant=merchant_for(category, rng),
                category=category,
                amount=amount,
                purchase_date=purchase_date,
                payment_amount_on_card=payment,
                event_type=event_type,
                event_date=purchase_date + timedelta(days=offset),
                delay_hours=delay_hours,
                evidence_available=evidence,
            )

        draft["ground_truth"] = label_transaction(draft, benefits)
        if draft["ground_truth"]["eligible"] == want_eligible:
            return draft
    raise RuntimeError(f"Could not build a {'eligible' if want_eligible else 'ineligible'} transaction")


def assign_ids(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        ordered.append({"transaction_id": f"txn_{index:04d}", **record})
    return ordered


def validate(records: list[dict[str, Any]], benefits: list[dict[str, Any]]) -> None:
    if not 200 <= len(records) <= 500:
        raise SystemExit(f"Expected 200-500 transactions, found {len(records)}")
    eligible = [record for record in records if record["ground_truth"]["eligible"]]
    ratio = len(eligible) / len(records)
    if not 0.45 <= ratio <= 0.55:
        raise SystemExit(f"Eligible ratio {ratio:.2f} is outside 45-55%")
    covered = {record["ground_truth"]["benefit_type"] for record in eligible}
    if covered != {"purchase_protection", "return_protection", "trip_delay_insurance"}:
        raise SystemExit(f"Eligible benefit types are incomplete: {covered}")

    def has_window_edge(issuer: str, card_name: str, window: int, day: int, eligible_flag: bool) -> bool:
        for record in records:
            if record["issuer"] != issuer or record["card_name"] != card_name:
                continue
            event_date = record["event"].get("event_date")
            if not event_date:
                continue
            elapsed = (date.fromisoformat(event_date) - date.fromisoformat(record["purchase_date"])).days
            truth = record["ground_truth"]
            if (
                elapsed == day
                and truth["eligible"] is eligible_flag
                and truth["benefit_type"] == "purchase_protection"
            ):
                return True
        return False

    chase = next(
        benefit
        for benefit in benefits
        if benefit["issuer"] == "Chase" and benefit["benefit_type"] == "purchase_protection"
    )
    window = int(chase["coverage_window_days"])
    if not has_window_edge("Chase", "Sapphire Preferred", window, window, True):
        raise SystemExit("Missing eligible purchase on the last covered day")
    if not has_window_edge("Chase", "Sapphire Preferred", window, window + 1, False):
        raise SystemExit("Missing rejected purchase one day past the window")

    def has_delay(issuer: str, hours: int, eligible_flag: bool) -> bool:
        return any(
            record["issuer"] == issuer
            and record["event"]["event_type"] == "flight_delay"
            and record["event"]["delay_hours"] == hours
            and record["ground_truth"]["eligible"] is eligible_flag
            for record in records
        )

    if not has_delay("American Express", 6, True) or not has_delay("American Express", 5, False):
        raise SystemExit("Missing the 6-hour Amex delay boundary")
    if not has_delay("Chase", 12, True) or not has_delay("Chase", 11, False):
        raise SystemExit("Missing the 12-hour Chase delay boundary")
    if not any(
        record["issuer"] == "Citi"
        and record["event"]["event_type"] == "store_return_denied"
        and record["ground_truth"]["eligible"] is False
        and record["ground_truth"]["benefit_type"] is None
        for record in records
    ):
        raise SystemExit("Missing a Citi return-protection rejection")


def generate(benefits_path: Path, output_path: Path, seed: int = 42) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    benefits = load_benefits(benefits_path)
    records = fixed_cases(benefits, rng)
    while len(records) < TARGET_COUNT:
        eligible_so_far = sum(record["ground_truth"]["eligible"] for record in records)
        records.append(random_case(rng, benefits, want_eligible=eligible_so_far < TARGET_COUNT / 2))
    records = assign_ids(records)
    validate(records, benefits)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return records


def summarize(records: list[dict[str, Any]]) -> None:
    eligible = [record for record in records if record["ground_truth"]["eligible"]]
    print(f"Wrote {len(records)} transactions ({len(eligible)} eligible, {len(records) - len(eligible)} not eligible)")
    for benefit_type in ("purchase_protection", "return_protection", "trip_delay_insurance"):
        matched = [
            record
            for record in records
            if record["ground_truth"]["benefit_type"] == benefit_type and record["ground_truth"]["eligible"]
        ]
        print(f"  eligible {benefit_type}: {len(matched)}")


if __name__ == "__main__":
    dataset = generate(ROOT / "benefits_data.json", ROOT / "data" / "transactions.json")
    summarize(dataset)
