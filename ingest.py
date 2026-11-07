"""Extract searchable, section-aware chunks from benefit-guide PDFs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BENEFIT_HEADINGS = {
    "purchase protection": "purchase_protection",
    "purchase security": "purchase_protection",
    "damage and theft": "purchase_protection",
    "return protection": "return_protection",
    "trip delay insurance": "trip_delay_insurance",
    "trip delay reimbursement": "trip_delay_insurance",
    "trip delay": "trip_delay_insurance",
}
HEADING_RE = re.compile(
    r"(?im)^\s*(purchase protection|purchase security|damage and theft|return protection|trip delay insurance|trip delay reimbursement|trip delay)\s*$"
)


def split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("general", text.strip())] if text.strip() else []

    sections: list[tuple[str, str]] = []
    prefix = text[: matches[0].start()].strip()
    if prefix:
        sections.append(("general", prefix))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = text[match.end() : end].strip()
        if section_text:
            heading = match.group(1).lower()
            sections.append((BENEFIT_HEADINGS[heading], section_text))
    return sections


def build_chunks(pdf_path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    chunks: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        for section, text in split_sections(page_text):
            chunks.append(
                {
                    "chunk_id": f"{pdf_path.stem}-p{page_number}-{len(chunks)}",
                    "text": text,
                    "issuer": source["issuer"],
                    "card_name": source["card_name"],
                    "benefit_type": section,
                    "document_title": source["document_title"],
                    "source_url": source["url"],
                    "source_status": source.get("source_status", "official_issuer_source"),
                    "filename": pdf_path.name,
                    "page": page_number,
                }
            )
    return chunks


def ingest(manifest_path: Path, pdf_dir: Path, output_path: Path) -> None:
    sources = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_chunks: list[dict[str, Any]] = []
    for source in sources:
        pdf_path = pdf_dir / source["filename"]
        if not pdf_path.exists():
            print(f"Skipping missing PDF: {pdf_path}")
            continue
        try:
            chunks = build_chunks(pdf_path, source)
        except Exception as error:
            print(f"Skipping unreadable PDF {pdf_path.name}: {error}")
            continue
        all_chunks.extend(chunks)
        print(f"  {pdf_path.name}: {len(chunks)} chunks")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")
    print(f"Wrote {len(all_chunks)} chunks to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.json"))
    parser.add_argument("--pdf-dir", type=Path, default=Path("data/policy_pdfs"))
    parser.add_argument("--output", type=Path, default=Path("data/chunks.json"))
    args = parser.parse_args()
    ingest(args.manifest, args.pdf_dir, args.output)
