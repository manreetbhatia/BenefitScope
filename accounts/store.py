"""Signup, login, and the purchases recorded on each person's cards.

Passwords are stored as a salted hash. The starter purchase list is copied
from the sample transactions for the cards chosen at signup. Purchases added
later belong only to that account.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any


HASH_ROUNDS = 120_000


def card_label(issuer: str, card_name: str) -> str:
    return f"{issuer} {card_name}"


def parse_card_label(label: str, cards: list[tuple[str, str]]) -> tuple[str, str]:
    for issuer, card_name in cards:
        if card_label(issuer, card_name) == label:
            return issuer, card_name
    raise ValueError(f"Unknown card: {label}")


def available_cards(transactions: list[dict[str, Any]]) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for record in transactions:
        pair = (record["issuer"], record["card_name"])
        if pair not in seen:
            seen.append(pair)
    return seen


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), HASH_ROUNDS)
    return digest.hex()


def _public(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user["username"],
        "name": user["name"],
        "cards": list(user["cards"]),
        "purchases": list(user["purchases"]),
    }


def seed_purchases(
    transactions: list[dict[str, Any]],
    cards: list[dict[str, str]],
    limit_per_card: int = 6,
) -> list[dict[str, Any]]:
    """Copy a short, distinct sample history for the cards this person holds."""
    chosen: list[dict[str, Any]] = []
    for card in cards:
        seen: set[tuple[Any, ...]] = set()
        count = 0
        for record in transactions:
            if record["issuer"] != card["issuer"] or record["card_name"] != card["card_name"]:
                continue
            key = (record["merchant"], record["purchase_date"], record["category"], record["amount"])
            if key in seen:
                continue
            seen.add(key)
            chosen.append(
                {
                    "purchase_id": record["transaction_id"],
                    "issuer": record["issuer"],
                    "card_name": record["card_name"],
                    "item": str(record["category"]).replace("_", " "),
                    "merchant": record["merchant"],
                    "amount": record["amount"],
                    "purchase_date": record["purchase_date"],
                    "source": "sample",
                }
            )
            count += 1
            if count >= limit_per_card:
                break
    chosen.sort(key=lambda item: item["purchase_date"], reverse=True)
    return chosen


class AccountStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return list(payload.get("users", []))

    def _save(self, users: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"users": users}, indent=2), encoding="utf-8")

    def signup(
        self,
        username: str,
        password: str,
        name: str,
        cards: list[dict[str, str]],
        transactions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        username = username.strip().lower()
        name = " ".join(name.split())
        if len(username) < 3 or not username.replace("_", "").isalnum():
            raise ValueError("Username must be at least 3 letters or numbers.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        if not name:
            raise ValueError("Enter the name to show on the account.")
        if not cards:
            raise ValueError("Select at least one card.")
        users = self._load()
        if any(user["username"] == username for user in users):
            raise ValueError("That username is already taken.")
        salt = secrets.token_hex(16)
        record = {
            "username": username,
            "name": name,
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "cards": cards,
            "purchases": seed_purchases(transactions, cards),
        }
        users.append(record)
        self._save(users)
        return _public(record)

    def login(self, username: str, password: str) -> dict[str, Any] | None:
        username = username.strip().lower()
        for user in self._load():
            if user["username"] != username:
                continue
            digest = _hash_password(password, user["salt"])
            if secrets.compare_digest(digest, user["password_hash"]):
                return _public(user)
            return None
        return None

    def get(self, username: str) -> dict[str, Any] | None:
        username = username.strip().lower()
        for user in self._load():
            if user["username"] == username:
                return _public(user)
        return None

    def add_purchase(
        self,
        username: str,
        issuer: str,
        card_name: str,
        item: str,
        merchant: str,
        amount: float,
        purchase_date: str,
    ) -> dict[str, Any]:
        username = username.strip().lower()
        item = " ".join(item.split())
        merchant = " ".join(merchant.split())
        if not item or not merchant:
            raise ValueError("Enter what was bought and which store.")
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        users = self._load()
        for user in users:
            if user["username"] != username:
                continue
            held = {(card["issuer"], card["card_name"]) for card in user["cards"]}
            if (issuer, card_name) not in held:
                raise ValueError("That card is not on this account.")
            purchase = {
                "purchase_id": f"own_{secrets.token_hex(4)}",
                "issuer": issuer,
                "card_name": card_name,
                "item": item,
                "merchant": merchant,
                "amount": round(float(amount), 2),
                "purchase_date": purchase_date,
                "source": "entered",
            }
            user["purchases"].insert(0, purchase)
            user["purchases"].sort(key=lambda item: item["purchase_date"], reverse=True)
            self._save(users)
            return purchase
        raise ValueError("Account not found.")
