"""Each account keeps its own cards and purchase history."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from accounts.store import AccountStore


TRANSACTIONS = [
    {
        "transaction_id": "txn_0001",
        "issuer": "Chase",
        "card_name": "Sapphire Preferred",
        "merchant": "B&H Photo",
        "category": "electronics",
        "amount": 220.0,
        "purchase_date": "2026-06-01",
    },
    {
        "transaction_id": "txn_0002",
        "issuer": "Chase",
        "card_name": "Sapphire Preferred",
        "merchant": "B&H Photo",
        "category": "electronics",
        "amount": 220.0,
        "purchase_date": "2026-06-01",
    },
    {
        "transaction_id": "txn_0091",
        "issuer": "Capital One",
        "card_name": "Venture X",
        "merchant": "Apple",
        "category": "electronics",
        "amount": 300.0,
        "purchase_date": "2026-07-02",
    },
]


class AccountStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = AccountStore(Path(self.directory.name) / "users.json")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_signup_copies_only_the_selected_cards(self) -> None:
        user = self.store.signup(
            "alex",
            "secret1",
            "Alex Kim",
            [{"issuer": "Chase", "card_name": "Sapphire Preferred"}],
            TRANSACTIONS,
        )
        self.assertEqual(user["username"], "alex")
        self.assertEqual(len(user["purchases"]), 1)
        purchase = user["purchases"][0]
        self.assertEqual(purchase["merchant"], "B&H Photo")
        self.assertEqual(purchase["item"], "electronics")
        self.assertEqual(purchase["purchase_date"], "2026-06-01")
        self.assertEqual(purchase["card_name"], "Sapphire Preferred")
        saved = self.store.get("alex")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertNotIn("password_hash", saved)

    def test_login_rejects_a_wrong_password_and_a_duplicate_name(self) -> None:
        cards = [{"issuer": "Chase", "card_name": "Sapphire Preferred"}]
        self.store.signup("alex", "secret1", "Alex Kim", cards, TRANSACTIONS)
        self.assertIsNone(self.store.login("alex", "wrong-password"))
        logged_in = self.store.login("Alex", "secret1")
        self.assertIsNotNone(logged_in)
        with self.assertRaises(ValueError):
            self.store.signup("alex", "secret1", "Someone Else", cards, TRANSACTIONS)

    def test_added_purchase_stays_on_that_account_only(self) -> None:
        chase = [{"issuer": "Chase", "card_name": "Sapphire Preferred"}]
        capital = [{"issuer": "Capital One", "card_name": "Venture X"}]
        self.store.signup("alex", "secret1", "Alex Kim", chase, TRANSACTIONS)
        self.store.signup("blair", "secret2", "Blair Jones", capital, TRANSACTIONS)
        self.store.add_purchase(
            "alex",
            "Chase",
            "Sapphire Preferred",
            "Sony TV 65 inches",
            "xyz store",
            899,
            "2026-08-01",
        )
        alex = self.store.get("alex")
        blair = self.store.get("blair")
        assert alex is not None and blair is not None
        self.assertEqual(alex["purchases"][0]["item"], "Sony TV 65 inches")
        self.assertEqual(alex["purchases"][0]["purchase_date"], "2026-08-01")
        self.assertTrue(all(item["item"] != "Sony TV 65 inches" for item in blair["purchases"]))
        self.assertEqual(blair["purchases"][0]["merchant"], "Apple")


if __name__ == "__main__":
    unittest.main()
