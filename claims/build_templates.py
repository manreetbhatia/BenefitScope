"""Build the three Word claim-form templates.

Run from the project root:

    python -m claims.build_templates

Each field lives in its own table cell as a single {{placeholder}} run so
pipeline.py can replace the token without splitting Word runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor

from claims.placeholders import (
    EVIDENCE_BY_BENEFIT,
    EVIDENCE_LABELS,
    token,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "claims" / "templates"

INK = RGBColor(0x1A, 0x28, 0x20)
MUTED = RGBColor(0x3E, 0x4F, 0x46)
RULE = "C9D5CD"
HEADER_FILL = "D5E0D8"

FORMS: tuple[dict[str, str], ...] = (
    {
        "benefit_type": "purchase_protection",
        "title": "Purchase protection claim",
        "filename": "purchase_protection.docx",
        "purpose": (
            "Use this form after theft or damage of an item charged to the card. "
            "BenefitScope fills the placeholders from the eligibility check. "
            "It does not send this packet to the issuer."
        ),
        "incident_prompt": (
            "Describe what happened to the item (theft or damage), when it happened, "
            "and where."
        ),
    },
    {
        "benefit_type": "return_protection",
        "title": "Return protection claim",
        "filename": "return_protection.docx",
        "purpose": (
            "Use this form when the store will not take back an unused item charged "
            "to the card. BenefitScope fills the placeholders from the eligibility "
            "check. It does not send this packet to the issuer."
        ),
        "incident_prompt": (
            "Describe the return attempt: the store, the date, and how the return "
            "was refused."
        ),
    },
    {
        "benefit_type": "trip_delay_insurance",
        "title": "Trip delay insurance claim",
        "filename": "trip_delay_insurance.docx",
        "purpose": (
            "Use this form after a common-carrier delay on a trip paid with the card. "
            "BenefitScope fills the placeholders from the eligibility check. "
            "It does not send this packet to the issuer."
        ),
        "incident_prompt": (
            "Describe the delay: carrier, route, hours delayed, and the extra costs "
            "you paid."
        ),
    },
)


def _set_run(run, *, size: int = 11, bold: bool = False, color: RGBColor = INK) -> None:
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def _shade_cell(cell, fill: str) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:shd"))
    if existing is not None:
        tc_pr.remove(existing)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)


def _set_cell_border(cell) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), RULE)
        tc_borders.append(element)


def _write_cell(cell, text: str, *, bold: bool = False, size: int = 11, color: RGBColor = INK) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(text)
    _set_run(run, size=size, bold=bold, color=color)
    _set_cell_border(cell)


def _add_heading(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(16)
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(text)
    _set_run(run, size=13, bold=True)


def _add_note(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run(text)
    _set_run(run, size=10, color=MUTED)


def _add_field_table(document: Document, rows: list[tuple[str, str]]) -> None:
    table = document.add_table(rows=len(rows), cols=2)
    table.autofit = True
    for index, (label, field) in enumerate(rows):
        left, right = table.rows[index].cells
        _write_cell(left, label, bold=True, size=10, color=MUTED)
        _write_cell(right, token(field))
        _shade_cell(left, HEADER_FILL)
        left.width = Inches(2.4)
        right.width = Inches(4.4)


def _add_evidence_table(document: Document, evidence_fields: tuple[str, ...]) -> None:
    table = document.add_table(rows=1 + len(evidence_fields), cols=2)
    header_status, header_item = table.rows[0].cells
    _write_cell(header_status, "Attached", bold=True, size=10)
    _write_cell(header_item, "Document", bold=True, size=10)
    _shade_cell(header_status, HEADER_FILL)
    _shade_cell(header_item, HEADER_FILL)
    header_status.width = Inches(1.6)
    header_item.width = Inches(5.2)
    for index, field in enumerate(evidence_fields, start=1):
        status, item = table.rows[index].cells
        _write_cell(status, token(field))
        _write_cell(item, EVIDENCE_LABELS[field], size=11)
        status.width = Inches(1.6)
        item.width = Inches(5.2)
    note = document.add_paragraph()
    note.paragraph_format.space_before = Pt(6)
    run = note.add_run(
        "pipeline.py replaces each evidence placeholder with Yes, No, or Not required."
    )
    _set_run(run, size=9, color=MUTED)


def build_form(spec: dict[str, str]) -> Document:
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.9)
    section.bottom_margin = Inches(0.9)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)

    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    style.font.color.rgb = INK
    style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE

    mark = document.add_paragraph()
    mark.paragraph_format.space_after = Pt(2)
    run = mark.add_run("BenefitScope")
    _set_run(run, size=11, bold=True)

    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    run = title.add_run(spec["title"])
    _set_run(run, size=22, bold=True)

    _add_note(document, spec["purpose"])

    _add_heading(document, "Claim record")
    _add_field_table(
        document,
        [
            ("Claim id", "claim_id"),
            ("Prepared date", "prepared_date"),
        ],
    )

    _add_heading(document, "Claimant")
    _add_field_table(document, [("Claimant name", "claimant_name")])

    _add_heading(document, "Card")
    _add_field_table(
        document,
        [
            ("Issuer", "issuer"),
            ("Card name", "card_name"),
            ("Card last 4", "card_last_4"),
        ],
    )

    _add_heading(document, "Transaction")
    _add_field_table(
        document,
        [
            ("Transaction date", "transaction_date"),
            ("Transaction amount", "transaction_amount"),
            ("Merchant", "merchant"),
            ("Item", "item_description"),
        ],
    )

    _add_heading(document, "Incident")
    _add_note(document, spec["incident_prompt"])
    _add_field_table(
        document,
        [
            ("Incident date", "incident_date"),
            ("Incident description", "incident_description"),
        ],
    )

    _add_heading(document, "Requested reimbursement")
    _add_field_table(
        document,
        [("Requested reimbursement amount", "requested_reimbursement_amount")],
    )

    _add_heading(document, "Evidence checklist")
    _add_note(
        document,
        "Mark each document that is on file for this claim. Leave a row as "
        "Not required when that document does not apply to this event.",
    )
    _add_evidence_table(document, EVIDENCE_BY_BENEFIT[spec["benefit_type"]])

    close = document.add_paragraph()
    close.paragraph_format.space_before = Pt(18)
    run = close.add_run(
        "This packet is a draft for the cardholder. Filing stays with the issuer "
        "or the benefit administrator named in the guide."
    )
    _set_run(run, size=9, color=MUTED)
    close.alignment = WD_ALIGN_PARAGRAPH.LEFT
    return document


def write_templates(directory: Path = TEMPLATE_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in FORMS:
        path = directory / spec["filename"]
        build_form(spec).save(path)
        written.append(path)
    return written


def main() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    paths = write_templates()
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
