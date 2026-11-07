"""Shopping answers must quote uploaded guide pages and must not invent a discount."""

from __future__ import annotations

import unittest
from pathlib import Path

from eligibility.purchase_lookup import lookup_purchase, parse_purchase_prompt
from retriever import PolicyRetriever


ROOT = Path(__file__).resolve().parents[1]
RETRIEVER = PolicyRetriever(ROOT / "data" / "chunks.json")
PROMPT = "i want to buy a sony tv 65 inches from xyz store"
FLIGHT = "i want to buy a flight from delta"


def cited_pages(result: dict) -> set[tuple[str, int]]:
    pages: set[tuple[str, int]] = set()
    for group in ("purchase_protection", "return_protection", "other_pages"):
        for hit in result[group]:
            pages.add((hit["filename"], hit["page"]))
    return pages


class PurchaseLookupTests(unittest.TestCase):
    def test_tv_sentence_parses_item_store_and_size(self) -> None:
        parsed = parse_purchase_prompt(PROMPT)
        self.assertEqual(parsed["category"], "electronics")
        self.assertEqual(parsed["merchant"], "xyz store")
        self.assertEqual(parsed["size"], "65 inches")
        self.assertIn("sony tv", parsed["item"])
        self.assertIsNone(parsed["amount"])

    def test_tv_and_flight_cite_different_pages(self) -> None:
        tv = lookup_purchase(PROMPT, RETRIEVER, issuer="Chase")
        flight = lookup_purchase(FLIGHT, RETRIEVER, issuer="Chase")
        self.assertNotEqual(cited_pages(tv), cited_pages(flight))
        flight_types = {hit["benefit_type"] for hit in flight["other_pages"]}
        self.assertIn("trip_delay_insurance", flight_types)
        tv_types = {hit["benefit_type"] for hit in tv["purchase_protection"] + tv["other_pages"]}
        self.assertNotIn("trip_delay_insurance", tv_types)

    def test_chase_return_protection_cites_a_return_page(self) -> None:
        result = lookup_purchase(PROMPT, RETRIEVER, issuer="Chase")
        self.assertTrue(result["return_protection"])
        hit = result["return_protection"][0]
        self.assertEqual(hit["issuer"], "Chase")
        self.assertEqual(hit["benefit_type"], "return_protection")
        self.assertIn("return", hit["quote"].lower())

    def test_citi_return_protection_is_absent_from_the_guides(self) -> None:
        result = lookup_purchase(PROMPT, RETRIEVER, issuer="Citi", card_name="Strata Premier")
        self.assertEqual(result["return_protection"], [])

    def test_current_guides_do_not_invent_a_next_purchase_discount(self) -> None:
        result = lookup_purchase(PROMPT, RETRIEVER)
        self.assertEqual(result["next_purchase_offer"], [])
        self.assertNotIn("discount_percent", result)

    def test_card_filter_changes_the_cited_issuer(self) -> None:
        chase = lookup_purchase(PROMPT, RETRIEVER, issuer="Chase", card_name="Sapphire Preferred")
        amex = lookup_purchase(PROMPT, RETRIEVER, issuer="American Express", card_name="Platinum")
        chase_hit = chase["purchase_protection"][0]
        amex_hit = amex["purchase_protection"][0]
        self.assertEqual(chase_hit["issuer"], "Chase")
        self.assertEqual(chase_hit["card_name"], "Sapphire Preferred")
        self.assertEqual(amex_hit["issuer"], "American Express")
        self.assertEqual(amex_hit["card_name"], "Platinum")
        self.assertNotEqual(chase_hit["filename"], amex_hit["filename"])


if __name__ == "__main__":
    unittest.main()
