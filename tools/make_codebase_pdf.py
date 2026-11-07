"""Generate a plain-language PDF that explains the BenefitScope codebase.

Design echoes the app: a serif display face (Times) for headings, a sans face
(Helvetica) for body, ink on a soft paper, and red used only as an accent.
Run:  python tools/make_codebase_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "BenefitScope_codebase_explained.pdf"

# Ledger palette
INK = (26, 40, 32)
MUTED = (62, 79, 70)
PAPER = (242, 245, 242)
RULE = (201, 213, 205)
SLIP = (255, 255, 255)
RED = (159, 29, 29)

LEFT = 20
RIGHT = 20
TOP = 20
WIDTH = 210 - LEFT - RIGHT


def clean(text: str) -> str:
    """Keep the text inside latin-1 so the core fonts never choke."""
    swaps = {
        "\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2192": "->",
        "\u2022": "-", "\u2265": ">=", "\u2264": "<=", "\u00d7": "x",
    }
    for bad, good in swaps.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


class Doc(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(LEFT, TOP, RIGHT)
        self.cover_page = True

    # Paper on every page, plus a footer, except the cover.
    def header(self) -> None:
        self.set_fill_color(*PAPER)
        self.rect(0, 0, 210, 297, style="F")
        if not self.cover_page:
            self.set_xy(LEFT, 10)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*MUTED)
            self.cell(0, 5, "BenefitScope", align="L")
            self.cell(0, 5, "How the codebase works", align="R")
            self.set_draw_color(*RULE)
            self.set_line_width(0.2)
            self.line(LEFT, 16, 210 - RIGHT, 16)

    def footer(self) -> None:
        if self.cover_page:
            return
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"{self.page_no()}", align="C")

    # --- building blocks ---
    def h1(self, text: str) -> None:
        self.ln(2)
        self.set_font("Times", "B", 20)
        self.set_text_color(*INK)
        self.multi_cell(WIDTH, 9, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*INK)
        self.set_line_width(0.4)
        y = self.get_y() + 1
        self.line(LEFT, y, LEFT + 18, y)
        self.ln(5)

    def h2(self, text: str) -> None:
        self.ln(2)
        self.set_font("Times", "B", 14)
        self.set_text_color(*INK)
        self.multi_cell(WIDTH, 7, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 10.5)
        self.set_text_color(*INK)
        self.multi_cell(WIDTH, 5.6, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                        markdown=True)
        self.ln(1.5)

    def bullet(self, text: str) -> None:
        self.set_font("Helvetica", "", 10.5)
        self.set_text_color(*INK)
        x = self.get_x()
        y = self.get_y()
        self.set_fill_color(*INK)
        self.rect(x, y + 1.7, 1.6, 1.6, style="F")
        indent = x + 5
        self.set_left_margin(indent)
        self.set_x(indent)
        self.multi_cell(WIDTH - 5, 5.6, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                        markdown=True)
        self.set_left_margin(LEFT)
        self.set_x(LEFT)
        self.ln(1.2)

    def step(self, number: int, title: str, text: str) -> None:
        self.set_font("Times", "B", 12)
        self.set_text_color(*RED)
        self.cell(8, 6, clean(str(number)), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*INK)
        self.cell(0, 6, clean(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_left_margin(LEFT + 8)
        self.set_x(LEFT + 8)
        self.set_font("Helvetica", "", 10.5)
        self.set_text_color(*MUTED)
        self.multi_cell(WIDTH - 8, 5.3, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_left_margin(LEFT)
        self.set_x(LEFT)
        self.ln(2)

    def file_row(self, name: str, what: str, shade: bool) -> None:
        self.set_font("Courier", "", 9)
        name_w = 62
        line_h = 5.0
        # measure wrapped height of the description
        self.set_font("Helvetica", "", 9.5)
        lines = self.multi_cell(WIDTH - name_w - 4, line_h, clean(what), dry_run=True,
                                output="LINES")
        rows = max(1, len(lines))
        block_h = rows * line_h + 2
        y0 = self.get_y()
        if shade:
            self.set_fill_color(*SLIP)
            self.rect(LEFT, y0, WIDTH, block_h, style="F")
        self.set_xy(LEFT + 1.5, y0 + 1)
        self.set_font("Courier", "", 9)
        self.set_text_color(*INK)
        self.multi_cell(name_w, line_h, clean(name), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_xy(LEFT + name_w + 2, y0 + 1)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*MUTED)
        self.multi_cell(WIDTH - name_w - 4, line_h, clean(what),
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y0 + block_h)

    def spacer(self, h: float = 2) -> None:
        self.ln(h)


def build() -> None:
    pdf = Doc()

    # ---------- Cover ----------
    pdf.add_page()
    pdf.cover_page = True
    pdf.set_fill_color(*PAPER)
    pdf.rect(0, 0, 210, 297, style="F")
    pdf.set_xy(LEFT, 46)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, "BENEFITSCOPE", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("Times", "B", 34)
    pdf.set_text_color(*INK)
    pdf.multi_cell(WIDTH, 14, "The codebase,\nin plain language",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.8)
    pdf.line(LEFT, pdf.get_y(), LEFT + 24, pdf.get_y())
    pdf.ln(8)
    pdf.set_font("Times", "", 13)
    pdf.set_text_color(*INK)
    pdf.multi_cell(
        WIDTH - 20, 7,
        clean(
            "A careful clerk that reads a credit card's own benefit guide and tells you, "
            "yes or no, whether a purchase is covered - and shows you the exact page, so it "
            "never has to be taken on faith."
        ),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        WIDTH, 5.4,
        clean(
            "What it covers: purchase protection, return protection, trip-delay insurance.\n"
            "Cards: Chase Sapphire Preferred, American Express Platinum, Citi Strata Premier, "
            "Capital One Venture X.\n"
            "Scope: a mid-term prototype. Purchases are sample or typed by the user; there is "
            "no live bank connection."
        ),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    # ---------- Section 1: The big idea ----------
    pdf.add_page()
    pdf.cover_page = False
    pdf.h1("The big idea")
    pdf.body(
        "Credit cards promise things like \"if your new TV is stolen, we will pay you back.\" "
        "But the real rules live in long PDF booklets, and every card sets different numbers. "
        "Most people cannot tell whether a theft, a refused return, or a delayed flight is "
        "actually covered."
    )
    pdf.body(
        "**BenefitScope reads those booklets for you.** It answers one question - *is this "
        "purchase covered, yes or no* - and it always shows the exact sentence from the "
        "booklet behind the answer. The guiding rule of the whole project: **never guess.** "
        "If a page does not state a number, the system refuses to invent one."
    )
    pdf.h2("The two questions it answers")
    pdf.bullet(
        "**Before you buy:** \"I want to buy a Sony TV from xyz store - what does my card "
        "cover?\" It returns the matching guide pages."
    )
    pdf.bullet(
        "**After something happens:** theft, damage, a denied return, or a delayed flight - "
        "\"can I make a claim?\" It returns a yes or no with the reason and the source page."
    )

    # ---------- Section 2: The pieces ----------
    pdf.add_page()
    pdf.h1("How it is built: the pieces")
    pdf.body(
        "Think of the project as rooms in a house. Each room does one job, and they hand work "
        "to each other in a line."
    )

    pdf.h2("1. The booklets - the raw material")
    pdf.bullet("`sources.json` lists 13 real card booklets to fetch.")
    pdf.bullet("`download_guides.py` downloads those PDFs.")
    pdf.bullet(
        "`ingest.py` splits each PDF into small page-by-page pieces and remembers which card "
        "and page each piece came from. The result is saved to `data/chunks.json`."
    )

    pdf.h2("2. The search - finding the right sentence")
    pdf.bullet(
        "`retriever.py` is a simple search engine over those pieces. Ask a question and it "
        "returns the most relevant paragraphs, each with a page number and a link. It uses an "
        "old, transparent method (TF-IDF) on purpose, so you can always see why a page was "
        "chosen."
    )

    pdf.h2("3. The hard rules - facts that need no opinion")
    pdf.bullet(
        "`benefits_data.json` stores the exact numbers for each card: the time window, the "
        "dollar cap, the delay hours, and the documents required (11 rule records)."
    )
    pdf.bullet(
        "`eligibility/rules.py` is the rulebook checker. It does the black-and-white checks: "
        "right card? inside the time window? police report provided for a theft? These are "
        "pure logic - no AI."
    )
    pdf.bullet(
        "`eligibility/prefilter.py` is a quick bouncer. If a purchase cannot possibly qualify "
        "(wrong card, too late, wrong category), it is rejected at once and the AI is never "
        "called. This saves money and prevents mistakes."
    )

    pdf.h2("4. The judge - where AI comes in, carefully")
    pdf.bullet(
        "`eligibility/reasoner.py` makes the decision. It runs the bouncer, pulls the matching "
        "booklet sentences, then sends the hard numbers *and* those sentences to an AI model "
        "(Groq) with strict instructions: use only what you are given, never invent a number, "
        "and if documents are missing the answer is no."
    )
    pdf.bullet(
        "A safety net: if the AI ever disagrees with the rulebook in a suspect way - for "
        "example, demanding a document the event does not need - the code trusts the rulebook, "
        "not the AI."
    )

    pdf.h2("5. The shopping helper")
    pdf.bullet(
        "`eligibility/purchase_lookup.py` reads a sentence like \"buy a Sony TV from xyz "
        "store,\" works out that it is electronics, and finds the booklet pages about purchase "
        "protection and returns - quoting a discount only if a page actually states one."
    )

    pdf.h2("6. Accounts, history, and samples")
    pdf.bullet(
        "`accounts/store.py` handles sign-up and login. Passwords are stored safely (a salted "
        "hash, never plain text). Each account sees only the cards that person picked."
    )
    pdf.bullet(
        "`data/generate_transactions.py` creates 400 made-up purchases, each already labelled "
        "yes or no from the rulebook, so accuracy can be measured. `eval/` runs those checks."
    )

    pdf.h2("7. The two front doors")
    pdf.bullet(
        "`frontend/app.py` is the website (built with Streamlit) - the tabs for checking "
        "purchases, browsing rules, and searching guides."
    )
    pdf.bullet(
        "`api/main.py` is the machine-to-machine version (FastAPI). Another program can send a "
        "purchase and get the same yes/no decision back as data."
    )

    # ---------- Section 3: One check, end to end ----------
    pdf.add_page()
    pdf.h1("How one check flows, end to end")
    pdf.body(
        "When you ask whether a purchase is covered, the work moves through five stages. The "
        "first three never call the AI."
    )
    pdf.step(1, "Quick bouncer (prefilter)",
             "Checks the hard facts: right card, the event matches the benefit, the category "
             "is allowed, the date or delay is inside the rule, and the card was actually "
             "charged. If it cannot qualify, the answer is \"No\" with a plain reason - and we "
             "stop here.")
    pdf.step(2, "Find the page (retriever)",
             "If it still looks possible, the search engine pulls the matching booklet page, "
             "plus the next page, because exclusions often sit there.")
    pdf.step(3, "Grounded decision (the model)",
             "The hard numbers and the short quote go to the AI with strict rules. It replies "
             "with a yes/no, a confidence, the quoted sentence, and the source page link.")
    pdf.step(4, "Safety checks",
             "The reply is compared against the rulebook. Missing required documents force a "
             "\"No.\" A model demand for an unneeded document is ignored in favour of the rule.")
    pdf.step(5, "The verdict",
             "You see the stamp: \"May qualify\" or \"Does not qualify,\" with the reason, the "
             "quoted sentence, and a link to the exact page.")

    # ---------- Section 4: Why trustworthy ----------
    pdf.h1("The one thing that makes it trustworthy")
    pdf.body(
        "Everywhere, the design refuses to guess. The hard numbers come from a rulebook; every "
        "quote is tied to a real page you can open; and the AI is boxed in so it cannot invent "
        "coverage. It is also honest where a benefit is absent - for example, Citi Strata "
        "Premier has no return protection, and the system says so instead of filling the gap."
    )

    # ---------- Section 5: File map ----------
    pdf.add_page()
    pdf.h1("File map")
    pdf.body("Where each job lives in the project.")
    rows = [
        ("sources.json", "The registry of 13 official guide PDFs to download."),
        ("download_guides.py", "Downloads the registered PDFs."),
        ("ingest.py", "Splits PDFs into page-level chunks (data/chunks.json)."),
        ("retriever.py", "TF-IDF search over the chunks; returns page + link."),
        ("benefits_data.json", "The 11 exact numeric rules: window, cap, delay, documents."),
        ("eligibility/rules.py", "Deterministic rulebook checks and the ground-truth labels."),
        ("eligibility/prefilter.py", "Rejects impossible claims before any AI call."),
        ("eligibility/reasoner.py", "Full decision: filter, retrieve, ask the model, safety-check."),
        ("eligibility/purchase_lookup.py", "Turns a shopping sentence into guide quotes."),
        ("llm_policy.py", "Talks to the Groq model and loads the API key."),
        ("accounts/store.py", "Sign-up and login (salted hash); per-user purchases."),
        ("data/generate_transactions.py", "Builds 400 labelled sample purchases."),
        ("data/transactions.json", "The 400 sample purchases with answers."),
        ("data/users.json", "Saved accounts (password hashes only)."),
        ("eval/ragas_eval.py", "Measures retrieval quality and eligibility accuracy."),
        ("frontend/app.py", "The Streamlit website (the user interface)."),
        ("api/main.py", "FastAPI endpoints for other programs."),
    ]
    # table header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*INK)
    pdf.set_fill_color(*RULE)
    pdf.cell(62, 6, "  File", border=0, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(WIDTH - 62, 6, "  What it does", border=0, fill=True,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for i, (name, what) in enumerate(rows):
        pdf.file_row(name, what, shade=(i % 2 == 0))

    # ---------- Section 6: Tech ----------
    pdf.h1("The tools used")
    pdf.bullet("**Python** for everything.")
    pdf.bullet("**pypdf** to read the PDFs (some Chase files also needed **cryptography**).")
    pdf.bullet("A **TF-IDF** search written inside the project - no heavy embedding index.")
    pdf.bullet("**Groq** chat model (openai/gpt-oss-20b), temperature 0, JSON output.")
    pdf.bullet("**FastAPI** for the data endpoints, **Streamlit** for the website.")
    pdf.bullet("**PBKDF2-SHA256** with a random salt for passwords; all data stays in local files.")

    pdf.output(str(OUT))
    print("WROTE", OUT)


if __name__ == "__main__":
    build()
