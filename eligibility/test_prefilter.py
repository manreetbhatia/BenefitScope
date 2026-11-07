"""Confirm the pre-filter keeps the right benefits for hand-picked purchases."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from eligibility.prefilter import prefilter
from eligibility.rules import hard_check_failure, load_benefits


ROOT = Path(__file__).resolve().parents[1]
BENEFITS = load_benefits(ROOT / "benefits_data.json")
TRANSACTIONS = json.loads((ROOT / "data" / "transactions.json").read_text(encoding="utf-8"))


def benefit_types(transaction: dict) -> list[str]:
    return [benefit["benefit_type"] for benefit in prefilter(transaction, BENEFITS)]


def first(predicate) -> dict:
    matches = [record for record in TRANSACTIONS if predicate(record)]
    if not matches:
        raise AssertionError("No transaction matched this case")
    return matches[0]


def elapsed_days(record: dict) -> int | None:
    event_date = record["event"].get("event_date")
    if not event_date:
        return None
    return (date.fromisoformat(event_date) - date.fromisoformat(record["purchase_date"])).days


class PrefilterTests(unittest.TestCase):
    def test_dataset_size_and_balance(self) -> None:
        self.assertGreaterEqual(len(TRANSACTIONS), 200)
        self.assertLessEqual(len(TRANSACTIONS), 500)
        eligible = sum(record["ground_truth"]["eligible"] for record in TRANSACTIONS)
        ratio = eligible / len(TRANSACTIONS)
        self.assertGreaterEqual(ratio, 0.45)
        self.assertLessEqual(ratio, 0.55)

    def test_last_covered_day_stays(self) -> None:
        record = first(
            lambda record: record["issuer"] == "Chase"
            and record["ground_truth"]["benefit_type"] == "purchase_protection"
            and record["ground_truth"]["eligible"]
            and elapsed_days(record) == 120
        )
        self.assertEqual(benefit_types(record), ["purchase_protection"])

    def test_one_day_past_the_window_is_dropped(self) -> None:
        record = first(
            lambda record: record["issuer"] == "Chase"
            and record["event"]["event_type"] == "theft"
            and elapsed_days(record) == 121
        )
        self.assertEqual(benefit_types(record), [])
        self.assertFalse(record["ground_truth"]["eligible"])

    def test_day_119_of_chase_window_stays(self) -> None:
        record = first(
            lambda record: record["issuer"] == "Chase"
            and record["ground_truth"]["eligible"]
            and record["ground_truth"]["benefit_type"] == "purchase_protection"
            and elapsed_days(record) == 119
        )
        self.assertIn("purchase_protection", benefit_types(record))

    def test_missing_documents_still_reach_the_reasoner(self) -> None:
        record = first(
            lambda record: record["ground_truth"]["benefit_type"] == "purchase_protection"
            and not record["ground_truth"]["eligible"]
            and "missing evidence" in record["ground_truth"]["reason"]
            and record["issuer"] == "Chase"
        )
        self.assertIn("purchase_protection", benefit_types(record))

    def test_amex_delay_boundary(self) -> None:
        on_time = first(
            lambda record: record["issuer"] == "American Express"
            and record["event"]["delay_hours"] == 6
            and record["ground_truth"]["eligible"]
        )
        too_short = first(
            lambda record: record["issuer"] == "American Express"
            and record["event"]["delay_hours"] == 5
            and not record["ground_truth"]["eligible"]
        )
        self.assertEqual(benefit_types(on_time), ["trip_delay_insurance"])
        self.assertEqual(benefit_types(too_short), [])

    def test_chase_delay_boundary(self) -> None:
        on_time = first(
            lambda record: record["issuer"] == "Chase"
            and record["event"]["delay_hours"] == 12
            and record["ground_truth"]["eligible"]
        )
        too_short = first(
            lambda record: record["issuer"] == "Chase"
            and record["event"]["delay_hours"] == 11
        )
        self.assertEqual(benefit_types(on_time), ["trip_delay_insurance"])
        self.assertEqual(benefit_types(too_short), [])

    def test_purchase_with_no_incident_matches_nothing(self) -> None:
        record = first(lambda record: record["event"]["event_type"] == "none")
        self.assertEqual(benefit_types(record), [])
        self.assertFalse(record["ground_truth"]["eligible"])

    def test_citi_has_no_return_protection(self) -> None:
        record = first(
            lambda record: record["issuer"] == "Citi" and record["event"]["event_type"] == "store_return_denied"
        )
        self.assertEqual(benefit_types(record), [])
        self.assertIsNone(record["ground_truth"]["benefit_type"])

    def test_partial_card_payment_fails_full_payment_rule(self) -> None:
        record = first(
            lambda record: record["issuer"] == "American Express"
            and record["event"]["event_type"] == "store_return_denied"
            and record["payment_amount_on_card"] < record["amount"]
            and record["category"] in {"electronics", "clothing", "household_goods"}
        )
        self.assertEqual(benefit_types(record), [])
        self.assertFalse(record["ground_truth"]["eligible"])

    def test_amount_over_the_cap_can_still_be_partial(self) -> None:
        record = first(
            lambda record: record["issuer"] == "Chase"
            and record["ground_truth"]["eligible"]
            and record["ground_truth"]["benefit_type"] == "purchase_protection"
            and record["amount"] > 500
        )
        self.assertIn("purchase_protection", benefit_types(record))
        self.assertIn("partial", record["ground_truth"]["reason"])

    def test_return_protection_boundary(self) -> None:
        record = first(
            lambda record: record["issuer"] == "Capital One"
            and record["ground_truth"]["benefit_type"] == "return_protection"
            and record["ground_truth"]["eligible"]
            and elapsed_days(record) == 90
        )
        self.assertEqual(benefit_types(record), ["return_protection"])

    def test_every_label_agrees_with_the_hard_checks(self) -> None:
        for record in TRANSACTIONS:
            found = benefit_types(record)
            truth = record["ground_truth"]
            if truth["eligible"]:
                self.assertIn(truth["benefit_type"], found)
                continue
            if truth["benefit_type"] is None:
                self.assertEqual(found, [])
                continue
            benefit = next(
                item
                for item in BENEFITS
                if item["issuer"] == record["issuer"]
                and item["card_name"] == record["card_name"]
                and item["benefit_type"] == truth["benefit_type"]
            )
            if hard_check_failure(record, benefit) is None:
                self.assertIn(truth["benefit_type"], found)
            else:
                self.assertNotIn(truth["benefit_type"], found)


if __name__ == "__main__":
    unittest.main()
