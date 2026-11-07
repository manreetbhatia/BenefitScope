"""Drop transactions that cannot match a benefit before any model is called."""

from __future__ import annotations

from typing import Any

from eligibility.rules import hard_check_failure


def prefilter(transaction: dict[str, Any], benefits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return benefit records this purchase could still qualify for.

    Hard checks only: same card, matching event, covered category, inside the
    coverage window or delay threshold, and a card payment that meets the
    rule. Missing documents are intentionally kept, so a later step can ask
    for them. Purchases above the dollar cap still pass, because partial
    reimbursement is allowed.
    """
    return [benefit for benefit in benefits if hard_check_failure(transaction, benefit) is None]
