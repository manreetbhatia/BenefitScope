"""Placeholder names used in the Word templates and later filled by pipeline.py.

Each token is a complete {{snake_case}} string so python-docx can replace it
in a single table cell without splitting runs.
"""

from __future__ import annotations

SHARED_FIELDS: tuple[str, ...] = (
    "claimant_name",
    "card_last_4",
    "issuer",
    "card_name",
    "transaction_date",
    "transaction_amount",
    "merchant",
    "incident_description",
    "requested_reimbursement_amount",
    "incident_date",
    "item_description",
    "claim_id",
    "prepared_date",
)

PURCHASE_PROTECTION_EVIDENCE: tuple[str, ...] = (
    "evidence_original_receipt",
    "evidence_card_statement",
    "evidence_police_report_if_theft",
    "evidence_photos_if_damage",
    "evidence_proof_of_other_coverage_denial_if_applicable",
)

RETURN_PROTECTION_EVIDENCE: tuple[str, ...] = (
    "evidence_original_receipt",
    "evidence_card_statement",
    "evidence_proof_merchant_refused_return",
    "evidence_item_undamaged_confirmation",
)

TRIP_DELAY_EVIDENCE: tuple[str, ...] = (
    "evidence_proof_of_delay_from_carrier",
    "evidence_itemized_receipts_for_expenses",
    "evidence_card_statement_showing_trip_payment",
    "evidence_card_statement_showing_round_trip_paid_in_full",
)

EVIDENCE_BY_BENEFIT: dict[str, tuple[str, ...]] = {
    "purchase_protection": PURCHASE_PROTECTION_EVIDENCE,
    "return_protection": RETURN_PROTECTION_EVIDENCE,
    "trip_delay_insurance": TRIP_DELAY_EVIDENCE,
}

EVIDENCE_LABELS: dict[str, str] = {
    "evidence_original_receipt": "Original or itemized receipt",
    "evidence_card_statement": "Card statement showing the charge",
    "evidence_police_report_if_theft": "Police report (theft)",
    "evidence_photos_if_damage": "Photos of the damage",
    "evidence_proof_of_other_coverage_denial_if_applicable": (
        "Denial from other coverage, if any applies"
    ),
    "evidence_proof_merchant_refused_return": "Proof the store refused the return",
    "evidence_item_undamaged_confirmation": "Confirmation the item is undamaged",
    "evidence_proof_of_delay_from_carrier": "Proof of delay from the carrier",
    "evidence_itemized_receipts_for_expenses": "Itemized receipts for delay expenses",
    "evidence_card_statement_showing_trip_payment": (
        "Card statement showing the trip payment"
    ),
    "evidence_card_statement_showing_round_trip_paid_in_full": (
        "Card statement showing the round trip paid in full"
    ),
}


def token(name: str) -> str:
    return "{{" + name + "}}"


def fields_for(benefit_type: str) -> tuple[str, ...]:
    return SHARED_FIELDS + EVIDENCE_BY_BENEFIT[benefit_type]
