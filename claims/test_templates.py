"""Confirm each claim template opens and contains every placeholder field."""

from __future__ import annotations

import unittest
from pathlib import Path

from docx import Document

from claims.build_templates import FORMS, TEMPLATE_DIR, write_templates
from claims.placeholders import fields_for, token


def document_text(path: Path) -> str:
    document = Document(path)
    parts: list[str] = []
    for paragraph in document.paragraphs:
        parts.append(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.written = write_templates(TEMPLATE_DIR)

    def test_three_templates_exist(self) -> None:
        names = {path.name for path in self.written}
        self.assertEqual(
            names,
            {
                "purchase_protection.docx",
                "return_protection.docx",
                "trip_delay_insurance.docx",
            },
        )
        for path in self.written:
            self.assertGreater(path.stat().st_size, 2000)

    def test_every_required_placeholder_is_present(self) -> None:
        required = {
            "claimant_name",
            "card_last_4",
            "issuer",
            "transaction_date",
            "transaction_amount",
            "merchant",
            "incident_description",
            "requested_reimbursement_amount",
        }
        for spec in FORMS:
            text = document_text(TEMPLATE_DIR / spec["filename"])
            with self.subTest(spec["benefit_type"]):
                for name in required:
                    self.assertIn(token(name), text)
                for name in fields_for(spec["benefit_type"]):
                    self.assertIn(token(name), text)
                self.assertIn("Evidence checklist", text)

    def test_placeholders_stay_in_one_piece(self) -> None:
        """pipeline.py can only replace a token that lives in a single run."""
        for spec in FORMS:
            document = Document(TEMPLATE_DIR / spec["filename"])
            expected = {token(name) for name in fields_for(spec["benefit_type"])}
            found: set[str] = set()
            for table in document.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                if run.text in expected:
                                    found.add(run.text)
            with self.subTest(spec["benefit_type"]):
                self.assertEqual(found, expected)


if __name__ == "__main__":
    unittest.main()
