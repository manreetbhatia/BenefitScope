"""Reasoner paths that do not need a model call."""

from __future__ import annotations

import unittest
from pathlib import Path

from eligibility.reasoner import reason
from eligibility.rules import load_benefits
from retriever import PolicyRetriever


ROOT = Path(__file__).resolve().parents[1]


class ReasonerGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.benefits = load_benefits(ROOT / "benefits_data.json")
        cls.retriever = PolicyRetriever(ROOT / "data" / "chunks.json")

    def test_citi_return_never_calls_the_model(self) -> None:
        transaction = {
            "transaction_id": "txn_test_citi",
            "issuer": "Citi",
            "card_name": "Strata Premier",
            "merchant": "Best Buy",
            "category": "electronics",
            "amount": 200,
            "currency": "USD",
            "purchase_date": "2026-07-01",
            "payment_amount_on_card": 200,
            "event": {"event_type": "store_return_denied", "event_date": "2026-07-20", "delay_hours": None},
            "evidence_available": ["original_receipt", "card_statement", "proof_merchant_refused_return"],
        }
        result = reason(transaction, self.benefits, self.retriever, api_key="not-used", model="not-used")
        self.assertFalse(result["eligible"])
        self.assertIsNone(result["benefit_type"])
        self.assertIn("does not offer return protection", result["reason"])

    def test_quiet_purchase_matches_nothing(self) -> None:
        transaction = {
            "transaction_id": "txn_test_none",
            "issuer": "Chase",
            "card_name": "Sapphire Preferred",
            "merchant": "Best Buy",
            "category": "electronics",
            "amount": 80,
            "currency": "USD",
            "purchase_date": "2026-06-01",
            "payment_amount_on_card": 80,
            "event": {"event_type": "none", "event_date": None, "delay_hours": None},
            "evidence_available": [],
        }
        result = reason(transaction, self.benefits, self.retriever, api_key="not-used", model="not-used")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["missing_evidence"], [])


if __name__ == "__main__":
    unittest.main()
