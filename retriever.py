"""Search policy chunks and return citations for a RAG prompt."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {"a", "an", "and", "are", "does", "for", "in", "is", "of", "the", "to", "what"}


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text.lower()) if token not in STOP_WORDS]


def tfidf_vectors(documents: list[list[str]]) -> list[dict[str, float]]:
    document_frequency: dict[str, int] = {}
    for document in documents:
        for token in set(document):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    vectors: list[dict[str, float]] = []
    document_count = len(documents)
    for document in documents:
        term_frequency: dict[str, int] = {}
        for token in document:
            term_frequency[token] = term_frequency.get(token, 0) + 1
        vectors.append(
            {
                token: (count / len(document)) * math.log((document_count + 1) / (frequency + 1))
                for token, count in term_frequency.items()
                for frequency in [document_frequency[token]]
            }
        )
    return vectors


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    numerator = sum(value * right.get(token, 0.0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


class PolicyRetriever:
    def __init__(self, chunks_path: Path) -> None:
        self.chunks: list[dict[str, Any]] = json.loads(chunks_path.read_text(encoding="utf-8"))
        if not self.chunks:
            raise ValueError("No chunks found. Download PDFs and run ingest.py first.")
        self.matrix = tfidf_vectors(
            [tokenize(f"{chunk['benefit_type']} {chunk['text']}") for chunk in self.chunks]
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        issuer: str | None = None,
        benefit_type: str | None = None,
    ) -> list[dict[str, Any]]:
        candidates = [
            (index, chunk)
            for index, chunk in enumerate(self.chunks)
            if (issuer is None or chunk["issuer"].lower() == issuer.lower())
            and (benefit_type is None or chunk["benefit_type"] == benefit_type)
        ]
        if not candidates:
            return []
        query_tokens = tokenize(query)
        query_vector = tfidf_vectors(
            [query_tokens]
            + [tokenize(f"{chunk['benefit_type']} {chunk['text']}") for chunk in self.chunks]
        )[0]
        ranked = sorted(
            ((cosine_similarity(query_vector, self.matrix[index]), chunk) for index, chunk in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        return [{**chunk, "score": round(float(score), 4)} for score, chunk in ranked[:top_k]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--chunks", type=Path, default=Path("data/chunks.json"))
    parser.add_argument("--issuer")
    parser.add_argument("--benefit-type")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    results = PolicyRetriever(args.chunks).search(
        args.query, args.top_k, args.issuer, args.benefit_type
    )
    for result in results:
        print(f"\n[{result['score']}] {result['issuer']} - {result['benefit_type']}")
        print(f"{result['document_title']} (page {result['page']})")
        print(result["text"][:1200])
        print(f"Citation: {result['source_url']}#page={result['page']}")


if __name__ == "__main__":
    main()
