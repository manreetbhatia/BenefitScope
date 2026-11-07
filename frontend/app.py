"""Demo screens for checking a purchase, browsing rules, and searching the guides."""

from __future__ import annotations

import json
import sys
from datetime import date
from html import escape
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from accounts.store import AccountStore, available_cards, card_label, parse_card_label  # noqa: E402
from claims.placeholders import EVIDENCE_BY_BENEFIT, EVIDENCE_LABELS  # noqa: E402
from eligibility.prefilter import prefilter  # noqa: E402
from eligibility.purchase_lookup import lookup_purchase  # noqa: E402
from eligibility.reasoner import DEFAULT_MODEL, reason  # noqa: E402
from eligibility.rules import load_benefits  # noqa: E402
from llm_policy import load_api_key  # noqa: E402
from retriever import PolicyRetriever  # noqa: E402


TRANSACTIONS_PATH = ROOT / "data" / "transactions.json"
SOURCES_PATH = ROOT / "sources.json"
USERS_PATH = ROOT / "data" / "users.json"
THEME_PATH = Path(__file__).with_name("theme.css")

BENEFIT_LABELS = {
    "purchase_protection": "Purchase protection",
    "return_protection": "Return protection",
    "trip_delay_insurance": "Trip delay insurance",
}

CLAIM_FORMS = {
    "purchase_protection": {
        "note": (
            "Use this form after theft or damage of an item charged to the card. "
            "This stays on the website. It is not sent to the issuer."
        ),
        "incident_prompt": "Describe the theft or damage: what happened, when, and where.",
    },
    "return_protection": {
        "note": (
            "Use this form when the store will not take back an unused item charged to the card. "
            "This stays on the website. It is not sent to the issuer."
        ),
        "incident_prompt": "Describe the return attempt: the store, the date, and how the return was refused.",
    },
    "trip_delay_insurance": {
        "note": (
            "Use this form after a common-carrier delay on a trip paid with the card. "
            "This stays on the website. It is not sent to the issuer."
        ),
        "incident_prompt": "Describe the delay: carrier, route, hours delayed, and the extra costs you paid.",
    },
}


def readable(value: str | None) -> str:
    if not value:
        return "None"
    return BENEFIT_LABELS.get(value, value.replace("_", " "))


def human_list(items: list[str]) -> str:
    words = [item.replace("_", " ") for item in items]
    if not words:
        return "nothing listed"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + ", and " + words[-1]


def external_link(url: str, label: str) -> str:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return escape(label)
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def paint() -> None:
    st.html(THEME_PATH)


def masthead() -> None:
    st.html(
        """
        <div class="masthead">
          <p class="product">BenefitScope</p>
          <h1>Does this card cover it?</h1>
          <p class="lede">The answer is a quoted page from that card's own guide. This does not connect to a bank, and it does not file a claim.</p>
        </div>
        """
    )


def topbar(user: dict) -> None:
    left, right = st.columns([3, 1], vertical_alignment="center")
    with left:
        st.html('<p class="product">BenefitScope</p>')
    with right:
        st.html(f'<p class="whoami">Signed in as {escape(user["name"])}</p>')
        if st.button("Log out", width="stretch"):
            st.session_state["username"] = None
            st.rerun()
    st.html('<hr class="topbar-rule" />')


def section(title: str, note: str) -> None:
    st.html(f'<h2 class="pagehead">{escape(title)}</h2><p class="pagenote">{escape(note)}</p>')


def show_stamp(eligible: bool, detail: str) -> None:
    kind = "qualify" if eligible else "decline"
    word = "May qualify" if eligible else "Does not qualify"
    st.html(
        f"""
        <div class="stamp stamp-{kind}">
          <p class="stamp-word">{word}</p>
          <p class="stamp-detail">{escape(detail)}</p>
        </div>
        """,
        width="content",
    )


def show_facts(lines: list[str]) -> None:
    items = "".join(f"<li>{escape(line)}</li>" for line in lines if line)
    st.html(f'<ul class="facts">{items}</ul>')


def load_transactions() -> list[dict]:
    return json.loads(TRANSACTIONS_PATH.read_text(encoding="utf-8"))


def load_sources() -> list[dict]:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def purchase_label(transaction: dict) -> str:
    event = transaction["event"]["event_type"].replace("_", " ")
    return (
        f"{transaction['transaction_id']}, {transaction['issuer']} {transaction['card_name']}, "
        f"{transaction['merchant']}, ${transaction['amount']:.2f}, {event}"
    )


def demo_ids(transactions: list[dict]) -> list[str]:
    """A short set that covers each benefit plus a clear rejection."""
    wanted = [
        lambda record: record["ground_truth"]["eligible"]
        and record["ground_truth"]["benefit_type"] == "purchase_protection"
        and record["issuer"] == "Chase"
        and record["amount"] <= 500,
        lambda record: record["ground_truth"]["eligible"]
        and record["ground_truth"]["benefit_type"] == "return_protection"
        and record["issuer"] == "Capital One",
        lambda record: record["ground_truth"]["eligible"]
        and record["ground_truth"]["benefit_type"] == "trip_delay_insurance"
        and record["issuer"] == "Chase",
        lambda record: record["issuer"] == "Chase"
        and record["event"]["event_type"] == "theft"
        and record["ground_truth"]["eligible"] is False
        and "past the" in record["ground_truth"]["reason"],
        lambda record: record["issuer"] == "American Express" and record["event"].get("delay_hours") == 5,
        lambda record: record["issuer"] == "Citi" and record["event"]["event_type"] == "store_return_denied",
    ]
    chosen: list[str] = []
    for predicate in wanted:
        match = next((record["transaction_id"] for record in transactions if predicate(record)), None)
        if match and match not in chosen:
            chosen.append(match)
    return chosen


@st.cache_resource
def indexes():
    return load_benefits(ROOT / "benefits_data.json"), PolicyRetriever(ROOT / "data" / "chunks.json")


def api_key() -> str:
    return load_api_key(ROOT / "api.env")


def show_result(result: dict) -> None:
    benefit = readable(result.get("benefit_type"))
    if result["eligible"]:
        detail = f"for {benefit.lower()}" if result.get("benefit_type") else "for a benefit on this card"
    else:
        detail = "for a claim on this purchase"
    show_stamp(bool(result["eligible"]), detail)
    if result.get("reason"):
        st.html(f'<p class="passage">{escape(result["reason"])}</p>')
    lines = []
    if result.get("benefit_type"):
        lines.append(f"The benefit is {benefit.lower()}.")
    confidence = result.get("confidence")
    if confidence is not None:
        lines.append(f"This check is {float(confidence):.0%} confident.")
    missing = [item.replace("_", " ") for item in (result.get("missing_evidence") or [])]
    if missing:
        lines.append(f"Still needed: {human_list(missing)}.")
    if lines:
        show_facts(lines)
    if result.get("cited_clause"):
        st.html('<h2 class="group">From the guide</h2>')
        st.html(f'<p class="passage">{escape(result["cited_clause"])}</p>')
    source = result.get("cited_source") or {}
    if source.get("url"):
        page = source.get("page")
        title = source.get("document_title") or "Source document"
        link = source["url"] if not page else f"{source['url']}#page={page}"
        page_text = f", page {page}" if page else ""
        st.html(f'<p class="citation">{external_link(link, title + page_text)}</p>')


def show_guide_hit(hit: dict) -> None:
    title = hit["document_title"]
    page = hit["page"]
    label = f"{hit['issuer']} {hit['card_name']}. {title}, page {page}"
    st.html(
        f'<p class="passage">{escape(hit["quote"])}</p>'
        f'<p class="citation">{external_link(f"{hit["source_url"]}#page={page}", label)}</p>'
    )


def show_guide_group(title: str, hits: list[dict], empty: str) -> None:
    st.html(f'<h2 class="group">{escape(title)}</h2>')
    if not hits:
        st.html(f'<p class="empty">{escape(empty)}</p>')
        return
    for hit in hits:
        show_guide_hit(hit)


def lookup_for_cards(prompt: str, retriever: PolicyRetriever, cards: list[tuple[str, str]]) -> dict:
    """Search each of this person's cards and keep the strongest guide hits."""
    if len(cards) == 1:
        issuer, card_name = cards[0]
        return lookup_purchase(prompt, retriever, issuer=issuer, card_name=card_name)
    merged = None
    for issuer, card_name in cards:
        result = lookup_purchase(prompt, retriever, issuer=issuer, card_name=card_name)
        if merged is None:
            merged = result
            continue
        for key in ("purchase_protection", "return_protection", "next_purchase_offer", "other_pages"):
            combined = merged[key] + result[key]
            combined.sort(key=lambda hit: hit["score"], reverse=True)
            limit = 4 if key == "other_pages" else 1
            kept = []
            seen = set()
            for hit in combined:
                marker = (hit["filename"], hit["page"], hit["benefit_type"])
                if marker in seen:
                    continue
                seen.add(marker)
                kept.append(hit)
                if len(kept) >= limit:
                    break
            merged[key] = kept
    return merged


def tab_ask(retriever: PolicyRetriever, owned_cards: list[tuple[str, str]]) -> None:
    section(
        "Ask about a purchase",
        "Type what you want to buy. The answer is a quote from the uploaded guide. "
        "A next-purchase discount shows only when a guide page states one.",
    )
    prompt = st.text_area(
        "What do you want to buy",
        value="i want to buy a sony tv 65 inches from xyz store",
        height=80,
    )
    options = ["All my cards"] + [card_label(issuer, name) for issuer, name in owned_cards]
    choice = st.selectbox("Card", options)
    if not st.button("Show benefit rules", type="primary"):
        return
    if not prompt.strip():
        st.warning("Type a purchase first.")
        return
    if choice == "All my cards":
        result = lookup_for_cards(prompt, retriever, owned_cards)
    else:
        issuer, card_name = parse_card_label(choice, owned_cards)
        result = lookup_purchase(prompt, retriever, issuer=issuer, card_name=card_name)
    parsed = result["parsed"]
    bits = [parsed["item"] or "that purchase"]
    if parsed.get("size") and parsed["size"] not in bits[0]:
        bits.append(parsed["size"])
    if parsed.get("merchant"):
        bits.append(f"from {parsed['merchant']}")
    card_text = f" Card: {choice}." if choice != "All my cards" else ""
    st.write(f"Read as: {' '.join(bits)}.{card_text}")
    for note in parsed["notes"]:
        st.warning(note)
    if parsed["merchant"]:
        st.caption(f"{parsed['merchant']} may have its own return window. That store policy is not in these guides.")
    show_guide_group(
        "Purchase protection",
        result["purchase_protection"],
        "No uploaded page states purchase protection for this card.",
    )
    show_guide_group(
        "Return protection",
        result["return_protection"],
        "No uploaded page states return protection for this card.",
    )
    show_guide_group(
        "Next purchase",
        result["next_purchase_offer"],
        "None of the uploaded guides state a discount on the next purchase.",
    )
    if result["other_pages"]:
        show_guide_group("Other matching pages", result["other_pages"], "")


def purchase_facts(transaction: dict) -> None:
    event = transaction["event"]
    lines = [
        f"{transaction['issuer']} {transaction['card_name']}.",
        (
            f"{transaction['merchant']}, {transaction['category'].replace('_', ' ')}, "
            f"${transaction['amount']:.2f}."
        ),
        (
            f"Purchased {transaction['purchase_date']}. "
            f"${transaction['payment_amount_on_card']:.2f} was charged to the card."
        ),
        f"What happened: {event['event_type'].replace('_', ' ')}.",
    ]
    if event.get("event_date"):
        lines.append(f"Event date: {event['event_date']}.")
    if event.get("delay_hours") is not None:
        lines.append(f"The delay was {event['delay_hours']} hours.")
    documents = transaction.get("evidence_available") or []
    if documents:
        lines.append(f"Documents on file: {human_list(documents)}.")
    else:
        lines.append("No documents are on file.")
    show_facts(lines)


def tab_check(transactions: list[dict], benefits: list[dict]) -> None:
    section(
        "Check a purchase",
        "Pick a sample purchase. The hard rules run first, and the guide is read "
        "only if the purchase still looks possible.",
    )
    by_id = {record["transaction_id"]: record for record in transactions}
    highlighted = demo_ids(transactions)
    choice = st.selectbox(
        "Sample purchase",
        options=highlighted + [record["transaction_id"] for record in transactions if record["transaction_id"] not in highlighted],
        format_func=lambda transaction_id: ("Sample: " if transaction_id in highlighted else "") + purchase_label(by_id[transaction_id]),
    )
    selected = by_id[choice]
    purchase_facts(selected)
    candidates = prefilter(selected, benefits)
    if candidates:
        names = human_list([readable(item["benefit_type"]) for item in candidates])
        st.html(f'<p class="empty">Possible on this card: {escape(names)}.</p>')
    else:
        st.html(
            '<p class="empty">No benefit on this card fits this purchase, so the guide will not be read.</p>'
        )

    if st.button("Check eligibility", type="primary"):
        try:
            key = api_key()
        except (OSError, ValueError) as error:
            st.error(f"Could not read the Groq key from api.env. {error}")
            return
        _benefits, retriever = indexes()
        with st.spinner("Reading the matching benefit rule and policy text..."):
            result = reason(selected, benefits, retriever, key, DEFAULT_MODEL)
        show_result(result)
        truth = selected["ground_truth"]
        with st.expander("Sample label"):
            outcome = "eligible" if truth["eligible"] else "not eligible"
            benefit_name = readable(truth.get("benefit_type")).lower()
            st.html(f'<p class="passage">The sample label says this purchase is {outcome} for {escape(benefit_name)}.</p>')
            st.html(f'<p class="passage">{escape(truth["reason"])}</p>')


def tab_purchases(transactions: list[dict]) -> None:
    section(
        "Sample purchases",
        "These 400 purchases are made up. Each yes or no is computed from the written benefit rules.",
    )
    issuers = ["All"] + sorted({record["issuer"] for record in transactions})
    benefit_types = ["All", "purchase_protection", "return_protection", "trip_delay_insurance", "none"]
    filters = st.columns(3)
    issuer = filters[0].selectbox("Card issuer", issuers)
    benefit = filters[1].selectbox("Benefit", benefit_types, format_func=lambda item: "All" if item == "All" else readable(None if item == "none" else item))
    outcome = filters[2].selectbox("Result", ["All", "Eligible", "Not eligible"])

    rows = []
    for record in transactions:
        truth = record["ground_truth"]
        if issuer != "All" and record["issuer"] != issuer:
            continue
        labeled = truth.get("benefit_type") or "none"
        if benefit != "All" and labeled != benefit:
            continue
        if outcome == "Eligible" and not truth["eligible"]:
            continue
        if outcome == "Not eligible" and truth["eligible"]:
            continue
        rows.append(
            {
                "Id": record["transaction_id"],
                "Card": f"{record['issuer']} {record['card_name']}",
                "Merchant": record["merchant"],
                "Amount": record["amount"],
                "Event": record["event"]["event_type"].replace("_", " "),
                "Eligible": "Yes" if truth["eligible"] else "No",
                "Benefit": readable(truth.get("benefit_type")),
                "Why": truth["reason"],
            }
        )
    st.write(f"{len(rows)} purchases")
    st.dataframe(rows, width="stretch", hide_index=True)


def payment_sentence(value: str) -> str:
    return {
        "any_amount_on_card": "Any amount charged to the card counts.",
        "partial_amount_on_card": "Part of the purchase must be charged to the card.",
        "full_amount_on_card": "The full purchase must be charged to the card.",
    }.get(value, value.replace("_", " ").capitalize() + ".")


def rule_lines(benefit: dict) -> list[str]:
    if benefit["benefit_type"] == "trip_delay_insurance":
        window = f"The delay must be at least {benefit['delay_threshold_hours']} hours."
    else:
        window = f"The coverage window is {benefit['coverage_window_days']} days."
    annual = benefit.get("max_annual_amount")
    yearly = f"${annual:,.0f}" if annual else "not stated"
    return [
        window,
        f"The cap per claim is ${benefit['max_coverage_amount']:,.0f}. The yearly cap is {yearly}.",
        f"This covers {human_list(benefit['eligible_categories'])}.",
        f"This does not cover {human_list(benefit['exclusions'])}.",
        f"Documents to have ready: {human_list(benefit['required_evidence'])}.",
        payment_sentence(benefit["payment_requirement"]),
        f"File the claim within {benefit['claim_filing_deadline_days']} days.",
    ]


def tab_rules(benefits: list[dict]) -> None:
    section(
        "Benefit rules",
        "The numbers behind each yes or no. They come from the issuer guides, "
        "not from the sample purchases.",
    )
    issuers = ["All"] + sorted({benefit["issuer"] for benefit in benefits})
    issuer = st.selectbox("Issuer", issuers, key="rule_issuer")
    shown = [benefit for benefit in benefits if issuer == "All" or benefit["issuer"] == issuer]
    for benefit in shown:
        title = f"{benefit['issuer']} {benefit['card_name']}: {readable(benefit['benefit_type'])}"
        with st.expander(title, expanded=issuer != "All"):
            show_facts(rule_lines(benefit))
            source = benefit["source"]
            st.html(f'<p class="citation">{external_link(source["url"], source["document_title"])}</p>')
            st.caption(source["retrieved_note"])


def tab_search(retriever: PolicyRetriever) -> None:
    section(
        "Search the guides",
        "Look up pages in the downloaded PDFs. This does not decide a claim.",
    )
    query = st.text_input("Question", value="What does purchase protection cover and exclude?")
    issuers = ["Any"] + sorted({chunk["issuer"] for chunk in retriever.chunks})
    benefit_types = ["Any", "purchase_protection", "return_protection", "trip_delay_insurance"]
    filters = st.columns(3)
    issuer = filters[0].selectbox("Issuer", issuers, key="search_issuer")
    benefit_type = filters[1].selectbox("Benefit", benefit_types, format_func=readable, key="search_benefit")
    top_k = filters[2].slider("Pages to show", min_value=1, max_value=8, value=4)
    if st.button("Search guides"):
        hits = retriever.search(
            query,
            top_k=top_k,
            issuer=None if issuer == "Any" else issuer,
            benefit_type=None if benefit_type == "Any" else benefit_type,
        )
        if not hits:
            st.warning("No matching page was found.")
            return
        for hit in hits:
            heading = f"{hit['issuer']} {hit['card_name']}: {readable(hit['benefit_type'])}, page {hit['page']}"
            with st.expander(heading, expanded=True):
                st.html(f'<p class="passage">{escape(hit["text"][:1200])}</p>')
                label = f"{hit['document_title']}, page {hit['page']}"
                st.html(
                    f'<p class="citation">{external_link(f"{hit["source_url"]}#page={hit["page"]}", label)}</p>'
                )


def tab_guides(sources: list[dict]) -> None:
    section(
        "Source documents",
        "Thirteen guides are registered. The files download to data/policy_pdfs.",
    )
    rows = []
    for source in sources:
        rows.append(
            {
                "Issuer": source["issuer"],
                "Card": source["card_name"],
                "Document": source["document_title"],
                "File": source["filename"],
                "Status": source.get("source_status", "official_issuer_source").replace("_", " "),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
    for source in sources:
        st.html(f'<p class="citation">{external_link(source["url"], source["document_title"])}</p>')


def account_store() -> AccountStore:
    return AccountStore(USERS_PATH)


def signed_in_user() -> dict | None:
    if "username" not in st.session_state:
        st.session_state["username"] = None
    if not st.session_state["username"]:
        return None
    user = account_store().get(st.session_state["username"])
    if user is None:
        st.session_state["username"] = None
        return None
    return user


def account_form(transactions: list[dict]) -> None:
    store = account_store()
    cards = available_cards(transactions)
    labels = [card_label(issuer, name) for issuer, name in cards]
    mode = st.radio("Account", ["Log in", "Sign up"], horizontal=True, label_visibility="collapsed")
    if mode == "Log in":
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            user = store.login(username, password)
            if user is None:
                st.error("That username and password do not match.")
            else:
                st.session_state["username"] = user["username"]
                st.rerun()
        return

    st.caption("The purchase list is limited to the cards you choose here.")
    with st.form("signup"):
        name = st.text_input("Name")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        chosen = st.multiselect("Cards you use", labels, placeholder="Select a card")
        submitted = st.form_submit_button("Create account", type="primary")
    if submitted:
        try:
            user = store.signup(
                username,
                password,
                name,
                [
                    {"issuer": issuer, "card_name": card_name}
                    for issuer, card_name in (parse_card_label(label, cards) for label in chosen)
                ],
                transactions,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state["username"] = user["username"]
            st.rerun()


def tab_history(user: dict) -> None:
    cards = ", ".join(card_label(card["issuer"], card["card_name"]) for card in user["cards"])
    section(
        "Your purchases",
        f"Cards on this account: {cards}. Starter rows are sample charges for these cards, "
        "and purchases you add stay on this account.",
    )
    rows = []
    for purchase in user["purchases"]:
        rows.append(
            {
                "Date": purchase["purchase_date"],
                "Card": card_label(purchase["issuer"], purchase["card_name"]),
                "What": purchase["item"],
                "Store": purchase["merchant"],
                "Amount": purchase["amount"],
            }
        )
    st.write(f"{len(rows)} purchases")
    st.dataframe(rows, width="stretch", hide_index=True)

    st.html('<h2 class="group">Add a purchase</h2>')
    owned = [(card["issuer"], card["card_name"]) for card in user["cards"]]
    with st.form("add_purchase"):
        item = st.text_input("What was bought", placeholder="Sony TV 65 inches")
        merchant = st.text_input("Store", placeholder="xyz store")
        columns = st.columns(3)
        amount = columns[0].number_input("Amount", min_value=0.01, value=100.0, step=1.0)
        purchase_date = columns[1].date_input("Date")
        card_choice = columns[2].selectbox("Card", [card_label(issuer, name) for issuer, name in owned])
        submitted = st.form_submit_button("Save purchase")
    if not submitted:
        return
    issuer, card_name = parse_card_label(card_choice, owned)
    try:
        account_store().add_purchase(
            user["username"],
            issuer,
            card_name,
            item,
            merchant,
            float(amount),
            purchase_date.isoformat(),
        )
    except ValueError as error:
        st.error(str(error))
    else:
        st.rerun()


def card_offers_benefit(
    benefits: list[dict], issuer: str, card_name: str, benefit_type: str
) -> bool:
    return any(
        benefit["issuer"] == issuer
        and benefit["card_name"] == card_name
        and benefit["benefit_type"] == benefit_type
        for benefit in benefits
    )


def show_claim_packet(draft: dict) -> None:
    st.html(f'<h2 class="group">{escape(readable(draft["benefit_type"]))} claim</h2>')
    lines = [
        f"Claimant: {draft['claimant_name']}.",
        f"Card: {draft['issuer']} {draft['card_name']}, last four {draft['card_last_4']}.",
        (
            f"Transaction: {draft['merchant']}, {draft['item_description']}, "
            f"${draft['transaction_amount']:.2f}, {draft['transaction_date']}."
        ),
        f"Incident date: {draft['incident_date']}.",
        draft["incident_description"],
        f"Requested reimbursement: ${draft['requested_reimbursement_amount']:.2f}.",
    ]
    attached = draft.get("evidence") or []
    if attached:
        lines.append("Documents on file: " + human_list(attached) + ".")
    else:
        lines.append("No documents are marked as on file.")
    show_facts(lines)


def tab_claim(user: dict, owned: list[tuple[str, str]], benefits: list[dict]) -> None:
    section(
        "File a claim",
        "Choose the benefit, fill the form on this page, and review the draft here. "
        "BenefitScope does not file the claim with the issuer.",
    )
    benefit_type = st.radio(
        "Benefit",
        list(CLAIM_FORMS),
        format_func=readable,
        horizontal=True,
        key="claim_benefit",
    )
    copy = CLAIM_FORMS[benefit_type]
    st.html(f'<p class="pagenote">{escape(copy["note"])}</p>')

    purchases = user.get("purchases") or []
    selected: dict | None = None
    if purchases:
        options = ["Start from a blank form"] + [
            f"{row['purchase_date']}, {card_label(row['issuer'], row['card_name'])}, "
            f"{row['item']}, {row['merchant']}, ${row['amount']:.2f}"
            for row in purchases
        ]
        choice = st.selectbox("Start from a purchase", options, key="claim_purchase")
        if choice != "Start from a blank form":
            selected = purchases[options.index(choice) - 1]

    default_card = card_label(owned[0][0], owned[0][1])
    default_item = ""
    default_merchant = ""
    default_amount = 100.0
    default_purchase_date = date.today()
    if selected:
        default_card = card_label(selected["issuer"], selected["card_name"])
        default_item = selected["item"]
        default_merchant = selected["merchant"]
        default_amount = float(selected["amount"])
        default_purchase_date = date.fromisoformat(selected["purchase_date"])

    card_labels = [card_label(issuer, name) for issuer, name in owned]
    if default_card not in card_labels:
        default_card = card_labels[0]

    with st.form("claim_form"):
        claimant_name = st.text_input("Claimant name", value=user["name"])
        card_choice = st.selectbox(
            "Card",
            card_labels,
            index=card_labels.index(default_card),
        )
        card_last_4 = st.text_input("Card last 4", max_chars=4, placeholder="1234")
        item_description = st.text_input("Item", value=default_item, placeholder="Sony TV 65 inches")
        merchant = st.text_input("Merchant", value=default_merchant, placeholder="xyz store")
        columns = st.columns(3)
        transaction_amount = columns[0].number_input(
            "Transaction amount", min_value=0.01, value=default_amount, step=1.0
        )
        transaction_date = columns[1].date_input("Transaction date", value=default_purchase_date)
        incident_date = columns[2].date_input("Incident date", value=date.today())
        incident_description = st.text_area(
            "Incident description",
            placeholder=copy["incident_prompt"],
            height=100,
        )
        requested = st.number_input(
            "Requested reimbursement amount",
            min_value=0.01,
            value=float(default_amount),
            step=1.0,
        )
        st.markdown("**Evidence checklist**")
        evidence_marks: dict[str, bool] = {}
        for field in EVIDENCE_BY_BENEFIT[benefit_type]:
            evidence_marks[field] = st.checkbox(EVIDENCE_LABELS[field], key=f"ev_{benefit_type}_{field}")
        submitted = st.form_submit_button("Prepare claim", type="primary")

    if submitted:
        issuer, card_name = parse_card_label(card_choice, owned)
        missing = []
        if not claimant_name.strip():
            missing.append("claimant name")
        if len((card_last_4 or "").strip()) != 4 or not (card_last_4 or "").strip().isdigit():
            missing.append("the last four digits of the card")
        if not item_description.strip():
            missing.append("the item")
        if not merchant.strip():
            missing.append("the merchant")
        if not incident_description.strip():
            missing.append("what happened")
        if missing:
            st.error("Fill in " + human_list(missing) + ".")
        elif not card_offers_benefit(benefits, issuer, card_name, benefit_type):
            st.error(
                f"{issuer} {card_name} does not offer {readable(benefit_type).lower()}. "
                "Pick a card that lists this benefit."
            )
        else:
            attached = [
                EVIDENCE_LABELS[field]
                for field, marked in evidence_marks.items()
                if marked
            ]
            st.session_state["prepared_claim"] = {
                "benefit_type": benefit_type,
                "claimant_name": claimant_name.strip(),
                "issuer": issuer,
                "card_name": card_name,
                "card_last_4": card_last_4.strip(),
                "item_description": item_description.strip(),
                "merchant": merchant.strip(),
                "transaction_amount": float(transaction_amount),
                "transaction_date": transaction_date.isoformat(),
                "incident_date": incident_date.isoformat(),
                "incident_description": incident_description.strip(),
                "requested_reimbursement_amount": float(requested),
                "evidence": attached,
            }
            st.rerun()

    draft = st.session_state.get("prepared_claim")
    if draft and draft.get("benefit_type") == benefit_type:
        show_claim_packet(draft)


def main() -> None:
    st.set_page_config(page_title="BenefitScope", layout="wide", initial_sidebar_state="collapsed")
    paint()
    benefits, retriever = indexes()
    transactions = load_transactions()
    sources = load_sources()
    user = signed_in_user()
    if user is None:
        masthead()
        account_form(transactions)
        return
    topbar(user)
    owned = [(card["issuer"], card["card_name"]) for card in user["cards"]]
    history, ask, check, claim, purchases, rules, search, guides = st.tabs(
        [
            "My purchases",
            "Ask about a purchase",
            "Check a purchase",
            "File a claim",
            "Sample purchases",
            "Benefit rules",
            "Search the guides",
            "Source documents",
        ]
    )
    with history:
        tab_history(user)
    with ask:
        tab_ask(retriever, owned)
    with check:
        tab_check(transactions, benefits)
    with claim:
        tab_claim(user, owned, benefits)
    with purchases:
        tab_purchases(transactions)
    with rules:
        tab_rules(benefits)
    with search:
        tab_search(retriever)
    with guides:
        tab_guides(sources)


if __name__ == "__main__":
    main()
else:
    main()
