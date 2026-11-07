"""Turn a shopping sentence into passages from the uploaded benefit guides.

The quotes come from the PDF index. This module does not fill in dollar
amounts from benefits_data.json, and it does not invent a next-purchase
discount when no guide page states one.
"""

from __future__ import annotations

import re
from typing import Any


CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "electronics": (
        "tv",
        "television",
        "laptop",
        "phone",
        "iphone",
        "camera",
        "headphone",
        "monitor",
        "computer",
        "tablet",
        "speaker",
        "console",
        "playstation",
        "xbox",
    ),
    "appliances": (
        "fridge",
        "refrigerator",
        "washer",
        "dryer",
        "dishwasher",
        "microwave",
        "oven",
        "appliance",
    ),
    "clothing": ("shirt", "shoe", "shoes", "dress", "jacket", "jeans", "clothing", "pants"),
    "jewelry": ("ring", "necklace", "bracelet", "jewelry", "jewellery"),
    "household_goods": ("furniture", "sofa", "couch", "mattress", "lamp", "rug"),
    "common_carrier_travel": (
        "flight",
        "airline",
        "airfare",
        "train ticket",
        "amtrak",
        "plane ticket",
    ),
}

TOPIC_QUERIES: tuple[tuple[str, str], ...] = (
    (r"\b(flight|airline|airfare|amtrak|plane ticket|train ticket)\b", "trip delay reimbursement"),
    (r"\brental car\b|\brental vehicle\b", "auto rental coverage"),
    (r"\bwarranty\b", "extended warranty protection"),
    (r"\b(luggage|baggage)\b", "baggage delay insurance"),
)

OFFER_RE = re.compile(
    r"\b(discount|statement credit|next purchase|percent off|%\s*off)\b",
    flags=re.IGNORECASE,
)

SCORE_FLOOR = 0.015
SEARCH_DEPTH = 40
QUOTE_CHARS = 500


def guide_cards(retriever: Any) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for chunk in retriever.chunks:
        pair = (chunk["issuer"], chunk["card_name"])
        if pair not in seen:
            seen.append(pair)
    return seen


def _category(text: str) -> str | None:
    lowered = f" {text.lower()} "
    best: tuple[int, str] | None = None
    for name, terms in CATEGORY_TERMS.items():
        hits = 0
        for term in terms:
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered):
                hits += 1
        if hits and (best is None or hits > best[0]):
            best = (hits, name)
    return None if best is None else best[1]


def _merchant(text: str) -> str | None:
    match = re.search(r"\b(?:from|at)\s+(.+)$", text.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    merchant = match.group(1).strip(" .")
    return merchant or None


def _item(text: str) -> str:
    without_store = re.sub(r"\b(?:from|at)\s+.+$", "", text.strip(), flags=re.IGNORECASE)
    without_lead = re.sub(
        r"^(?:i\s+)?(?:want\s+to\s+|would\s+like\s+to\s+|need\s+to\s+)?buy\s+(?:an?\s+)?",
        "",
        without_store.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", without_lead).strip(" .")
    return cleaned or text.strip()


def _size(text: str) -> str | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-?\s*)?(inch|inches|\"|in)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    number = match.group(1)
    if number.endswith(".0"):
        number = number[:-2]
    return f"{number} inches"


def _amount(text: str) -> float | None:
    match = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_purchase_prompt(prompt: str) -> dict[str, Any]:
    text = " ".join(prompt.split())
    notes: list[str] = []
    lowered = text.lower()
    if re.search(r"\b(used|refurbished|pre-owned|preowned)\b", lowered):
        notes.append(
            "The wording says this item is used or refurbished. "
            "These guides exclude used or pre-owned items from purchase protection."
        )
    if re.search(r"\b(final sale|as-is|as is)\b", lowered):
        notes.append("The wording says final sale or as-is. Return protection excludes items sold that way.")
    return {
        "item": _item(text),
        "merchant": _merchant(text),
        "category": _category(text),
        "size": _size(text),
        "amount": _amount(text),
        "notes": notes,
    }


def _quote(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= QUOTE_CHARS:
        return flat
    cut = flat[:QUOTE_CHARS].rsplit(" ", 1)[0]
    return cut + "..."


def _public(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "issuer": hit["issuer"],
        "card_name": hit["card_name"],
        "benefit_type": hit["benefit_type"],
        "document_title": hit["document_title"],
        "page": hit["page"],
        "source_url": hit["source_url"],
        "filename": hit["filename"],
        "score": hit["score"],
        "quote": _quote(hit["text"]),
    }


def _hit_key(hit: dict[str, Any]) -> tuple[str, int, str]:
    return (hit["filename"], hit["page"], hit["benefit_type"])


def _search(
    retriever: Any,
    query: str,
    issuer: str | None,
    card_name: str | None,
    benefit_type: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    hits = retriever.search(query, top_k=SEARCH_DEPTH, issuer=issuer, benefit_type=benefit_type)
    kept: list[dict[str, Any]] = []
    for hit in hits:
        if hit["score"] < SCORE_FLOOR:
            continue
        if card_name and hit["card_name"].lower() != card_name.lower():
            continue
        kept.append(_public(hit))
        if len(kept) >= limit:
            break
    return kept


def _related_pages(
    retriever: Any,
    prompt: str,
    issuer: str | None,
    card_name: str | None,
    used: set[tuple[str, int, str]],
) -> list[dict[str, Any]]:
    queries = [
        extra for pattern, extra in TOPIC_QUERIES if re.search(pattern, prompt, flags=re.IGNORECASE)
    ]
    queries.append(prompt)
    pages: list[dict[str, Any]] = []
    seen = set(used)
    for query in queries:
        for hit in _search(retriever, query, issuer, card_name, None, limit=5):
            key = _hit_key(hit)
            if key in seen:
                continue
            seen.add(key)
            pages.append(hit)
            if len(pages) >= 4:
                return pages
    return pages


def _next_purchase_offer(
    retriever: Any,
    prompt: str,
    parsed: dict[str, Any],
    issuer: str | None,
    card_name: str | None,
) -> list[dict[str, Any]]:
    """Keep a page only when its own text states a later-purchase discount."""
    item = parsed["item"] or prompt
    merchant = parsed["merchant"] or ""
    query = f"{item} {merchant} discount statement credit bonus next purchase"
    offers: list[dict[str, Any]] = []
    for hit in _search(retriever, query, issuer, card_name, None, limit=8):
        if OFFER_RE.search(hit["quote"]):
            offers.append(hit)
    return offers[:1]


def lookup_purchase(
    prompt: str,
    retriever: Any,
    issuer: str | None = None,
    card_name: str | None = None,
) -> dict[str, Any]:
    """Search the uploaded guides for this purchase. Numbers stay inside the quotes."""
    parsed = parse_purchase_prompt(prompt)
    item = parsed["item"] or prompt
    purchase = _search(
        retriever,
        f"{item} purchase protection",
        issuer,
        card_name,
        "purchase_protection",
        limit=1,
    )
    returns = _search(
        retriever,
        f"{item} return protection",
        issuer,
        card_name,
        "return_protection",
        limit=1,
    )
    used = {_hit_key(hit) for hit in purchase + returns}
    return {
        "parsed": parsed,
        "purchase_protection": purchase,
        "return_protection": returns,
        "next_purchase_offer": _next_purchase_offer(retriever, prompt, parsed, issuer, card_name),
        "other_pages": _related_pages(retriever, prompt, issuer, card_name, used),
    }
