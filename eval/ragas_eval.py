"""Measure whether search finds the right clause, and whether decisions match the labels."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eligibility.reasoner import gather_evidence, reason  # noqa: E402
from eligibility.rules import load_benefits  # noqa: E402
from llm_policy import load_api_key  # noqa: E402
from retriever import PolicyRetriever  # noqa: E402


def published_facts(benefit: dict[str, Any]) -> list[tuple[str, str]]:
    """Numbers a useful excerpt should contain: (kind, text to find)."""
    facts: list[tuple[str, str]] = []
    window = benefit.get("coverage_window_days")
    if window:
        facts.append(("window", str(window)))
    delay = benefit.get("delay_threshold_hours")
    if delay:
        facts.append(("delay", str(delay)))
    amount = int(benefit["max_coverage_amount"])
    rendered = f"{amount:,}" if amount >= 1000 else str(amount)
    facts.append(("amount", rendered))
    return facts


def fact_present(kind: str, fact: str, text: str) -> bool:
    if kind == "delay":
        return re.search(rf"(?<!\d){re.escape(fact)}\s*-?\s*hours?\b", text, flags=re.IGNORECASE) is not None
    if kind == "amount":
        compact = fact.replace(",", "")
        return (
            re.search(rf"(?<!\d){re.escape(fact)}(?!\d)", text) is not None
            or re.search(rf"(?<!\d){re.escape(compact)}(?!\d)", text) is not None
        )
    return re.search(rf"(?<!\d){re.escape(fact)}(?!\d)", text) is not None


def fact_recall(benefit: dict[str, Any], text: str) -> float:
    facts = published_facts(benefit)
    if not facts:
        return 0.0
    found = sum(1 for kind, fact in facts if fact_present(kind, fact, text))
    return found / len(facts)


def retrieval_report(retriever: PolicyRetriever, benefits: list[dict[str, Any]]) -> dict[str, Any]:
    """Score retrieval the way RAGAS describes context precision and context recall.

    A retrieved chunk is relevant when it is the same issuer and benefit, or it
    sits on the neighboring page of such a chunk. Context recall asks whether
    the retrieved text actually contains the benefit's published numbers.
    """
    rows = []
    for benefit in benefits:
        transaction = {
            "issuer": benefit["issuer"],
            "card_name": benefit["card_name"],
        }
        strict = retriever.search(
            f"what does {benefit['benefit_type'].replace('_', ' ')} cover and exclude",
            top_k=4,
            issuer=benefit["issuer"],
            benefit_type=benefit["benefit_type"],
        )
        strict = [chunk for chunk in strict if chunk["card_name"] == benefit["card_name"]]
        expanded = gather_evidence(retriever, transaction, benefit)
        strict_relevant = sum(
            1
            for chunk in strict
            if chunk["issuer"] == benefit["issuer"] and chunk["benefit_type"] == benefit["benefit_type"]
        )
        expanded_relevant = 0
        typed_pages = {
            (chunk["filename"], int(chunk["page"]))
            for chunk in retriever.chunks
            if chunk["issuer"] == benefit["issuer"]
            and chunk["card_name"] == benefit["card_name"]
            and chunk["benefit_type"] == benefit["benefit_type"]
        }
        for chunk in expanded:
            page = int(chunk["page"])
            nearby = any(
                chunk["filename"] == filename and abs(page - typed_page) <= 1
                for filename, typed_page in typed_pages
            )
            if chunk["benefit_type"] == benefit["benefit_type"] or nearby:
                expanded_relevant += 1
        strict_text = "\n".join(chunk.get("text") or "" for chunk in strict)
        expanded_text = "\n".join(chunk.get("text") or "" for chunk in expanded)
        rows.append(
            {
                "issuer": benefit["issuer"],
                "card_name": benefit["card_name"],
                "benefit_type": benefit["benefit_type"],
                "strict_hits": len(strict),
                "strict_precision": (strict_relevant / len(strict)) if strict else 0.0,
                "strict_fact_recall": fact_recall(benefit, strict_text),
                "expanded_hits": len(expanded),
                "expanded_precision": (expanded_relevant / len(expanded)) if expanded else 0.0,
                "expanded_fact_recall": fact_recall(benefit, expanded_text),
            }
        )

    def average(name: str, only_hits: str | None = None) -> float:
        pool = rows
        if only_hits:
            pool = [row for row in rows if row[only_hits] > 0]
        return sum(row[name] for row in pool) / len(pool) if pool else 0.0

    return {
        "queries": len(rows),
        "filtered_hit_rate": round(sum(row["strict_hits"] > 0 for row in rows) / len(rows), 3) if rows else 0.0,
        "expanded_hit_rate": round(sum(row["expanded_hits"] > 0 for row in rows) / len(rows), 3) if rows else 0.0,
        "context_precision_filtered": round(average("strict_precision", "strict_hits"), 3),
        "context_recall_filtered": round(average("strict_fact_recall"), 3),
        "context_precision_with_neighbor_pages": round(average("expanded_precision", "expanded_hits"), 3),
        "context_recall_with_neighbor_pages": round(average("expanded_fact_recall"), 3),
        "benefits_with_no_filtered_hit": [
            f"{row['issuer']} {row['card_name']} {row['benefit_type']}"
            for row in rows
            if row["strict_hits"] == 0
        ],
        "per_benefit": rows,
    }


def choose_sample(transactions: list[dict[str, Any]], per_group: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str | None, bool], list[dict[str, Any]]] = defaultdict(list)
    for transaction in transactions:
        truth = transaction["ground_truth"]
        groups[(truth.get("benefit_type"), bool(truth["eligible"]))].append(transaction)
    chosen: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda item: (str(item[0]), item[1])):
        chosen.extend(groups[key][:per_group])
    return chosen


def scores(pairs: list[tuple[bool, bool]]) -> dict[str, float | None]:
    true_positive = sum(predicted and actual for predicted, actual in pairs)
    false_positive = sum(predicted and not actual for predicted, actual in pairs)
    false_negative = sum((not predicted) and actual for predicted, actual in pairs)
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else None
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else None
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    accuracy = sum(predicted == actual for predicted, actual in pairs) / len(pairs) if pairs else None
    return {
        "count": len(pairs),
        "accuracy": None if accuracy is None else round(accuracy, 3),
        "precision": None if precision is None else round(precision, 3),
        "recall": None if recall is None else round(recall, 3),
        "f1": None if f1 is None else round(f1, 3),
    }


def eligibility_report(
    transactions: list[dict[str, Any]],
    benefits: list[dict[str, Any]],
    retriever: PolicyRetriever,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    predictions = []
    for index, transaction in enumerate(transactions, start=1):
        print(f"Checking {transaction['transaction_id']} ({index}/{len(transactions)})...", flush=True)
        result = reason(transaction, benefits, retriever, api_key, model)
        predictions.append(
            {
                "transaction_id": transaction["transaction_id"],
                "issuer": transaction["issuer"],
                "predicted_eligible": bool(result["eligible"]),
                "predicted_benefit_type": result.get("benefit_type"),
                "actual_eligible": bool(transaction["ground_truth"]["eligible"]),
                "actual_benefit_type": transaction["ground_truth"].get("benefit_type"),
                "reason": result.get("reason"),
                "confidence": result.get("confidence"),
                "decision_source": result.get("decision_source"),
                "checklist_override": bool(result.get("checklist_override")),
            }
        )
    overall_pairs = [(item["predicted_eligible"], item["actual_eligible"]) for item in predictions]
    by_type: dict[str, Any] = {}
    for benefit_type in ("purchase_protection", "return_protection", "trip_delay_insurance"):
        subset = [
            (item["predicted_eligible"], item["actual_eligible"])
            for item in predictions
            if item["actual_benefit_type"] == benefit_type
        ]
        by_type[benefit_type] = scores(subset)
    mistakes = [item for item in predictions if item["predicted_eligible"] != item["actual_eligible"]]
    sources: dict[str, int] = defaultdict(int)
    for item in predictions:
        sources[item.get("decision_source") or "unknown"] += 1
    model_pairs = [
        (item["predicted_eligible"], item["actual_eligible"])
        for item in predictions
        if item.get("decision_source") == "model"
    ]
    overrides = [item for item in predictions if item.get("checklist_override")]
    return {
        "overall": scores(overall_pairs),
        "model_only": scores(model_pairs),
        "decision_sources": dict(sources),
        "per_benefit_type": by_type,
        "mistakes": mistakes,
        "checklist_overrides": overrides,
        "predictions": predictions,
    }


def render_markdown(retrieval: dict[str, Any], eligibility: dict[str, Any] | None) -> str:
    lines = [
        "# Preliminary evaluation",
        "",
        "Transactions are synthetic. Benefit rules and policy guides are real.",
        "",
        "## Retrieval",
        "",
        "| Setup | Hit rate | Context precision | Context recall |",
        "| --- | ---: | ---: | ---: |",
        f"| Benefit-type filter only | {retrieval['filtered_hit_rate']:.3f} | {retrieval['context_precision_filtered']:.3f} | {retrieval['context_recall_filtered']:.3f} |",
        f"| Filter plus the neighboring page | {retrieval['expanded_hit_rate']:.3f} | {retrieval['context_precision_with_neighbor_pages']:.3f} | {retrieval['context_recall_with_neighbor_pages']:.3f} |",
        "",
        "Hit rate is the share of benefit records for which search returned at least one page.",
        "Context precision is the share of those pages that belong to the labeled benefit, or the page next to it. It is averaged only over searches that returned something.",
        "Context recall is the share of published numbers from the benefit record - day window, delay hours, dollar cap - found in the retrieved text. A benefit with no retrieved page scores zero.",
        "",
    ]
    if retrieval["benefits_with_no_filtered_hit"]:
        lines.append("These benefits had no page tagged with that benefit type:")
        lines.append("")
        for name in retrieval["benefits_with_no_filtered_hit"]:
            lines.append(f"- {name}")
        lines.append("")
    lines.extend(
        [
            "The chunker only labels a page when the benefit heading sits on its own line. Exclusions on the following page stay tagged `general`, and some benefits (notably American Express trip delay, which is not in the downloaded purchase/return PDFs) have no tagged page at all.",
            "",
        ]
    )
    if eligibility is None:
        lines.append("Eligibility accuracy was not run.")
        return "\n".join(lines)

    lines.extend(["## Eligibility", "", "| Slice | Count | Accuracy | Precision | Recall | F1 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    overall = eligibility["overall"]
    lines.append(
        f"| All sampled purchases | {overall['count']} | {overall['accuracy']} | {overall['precision']} | {overall['recall']} | {overall['f1']} |"
    )
    model_only = eligibility.get("model_only") or {}
    if model_only.get("count"):
        lines.append(
            f"| Model was actually asked | {model_only['count']} | {model_only['accuracy']} | {model_only['precision']} | {model_only['recall']} | {model_only['f1']} |"
        )
    for benefit_type, metrics in eligibility["per_benefit_type"].items():
        lines.append(
            f"| {benefit_type} | {metrics['count']} | {metrics['accuracy']} | {metrics['precision']} | {metrics['recall']} | {metrics['f1']} |"
        )
    lines.extend(["", "## Where it fails", ""])
    sources = eligibility.get("decision_sources") or {}
    if sources:
        rendered = ", ".join(f"{name} {count}" for name, count in sorted(sources.items()))
        lines.append(f"Who made the decision on this sample: {rendered}.")
        lines.append("")
    overrides = eligibility.get("checklist_overrides") or []
    if overrides:
        lines.append(
            "The model sometimes demands a document the benefit checklist does not require for that event "
            "(for example photos of damage on a theft claim). Those demands were ignored and the checklist was kept:"
        )
        lines.append("")
        for item in overrides:
            lines.append(f"- `{item['transaction_id']}` ({item['issuer']}, {item['actual_benefit_type']})")
        lines.append("")
    if not eligibility["mistakes"]:
        lines.append("On this sample, every eligible/not-eligible decision matched the label.")
    else:
        lines.append(f"{len(eligibility['mistakes'])} sampled purchases disagreed with the label:")
        lines.append("")
        for mistake in eligibility["mistakes"]:
            lines.append(
                f"- `{mistake['transaction_id']}` ({mistake['issuer']}, actual {mistake['actual_benefit_type']}={mistake['actual_eligible']}, "
                f"predicted {mistake['predicted_benefit_type']}={mistake['predicted_eligible']}): {mistake['reason']}"
            )
    lines.extend(
        [
            "",
            "Hard rejections (wrong card, wrong event, late date, delay too short, unpaid purchase) never call the model, so they stay aligned with the benefit table.",
            "The model is only asked after those checks pass. It can still disagree when a retrieved page does not mention the benefit, or when it treats a secondary-coverage clause as a rejection the labeled rule does not.",
            "Citi has no return-protection record on purpose. A denied store return on that card is labeled not eligible.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-group", type=int, default=4)
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    args = parser.parse_args()

    benefits = load_benefits(ROOT / "benefits_data.json")
    transactions = json.loads((ROOT / "data" / "transactions.json").read_text(encoding="utf-8"))
    retriever = PolicyRetriever(ROOT / "data" / "chunks.json")
    retrieval = retrieval_report(retriever, benefits)
    eligibility = None
    if not args.skip_llm:
        sample = choose_sample(transactions, args.per_group)
        eligibility = eligibility_report(sample, benefits, retriever, load_api_key(ROOT / "api.env"), args.model)

    output_dir = ROOT / "eval"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"retrieval": retrieval, "eligibility": eligibility}
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary = render_markdown(retrieval, eligibility)
    (output_dir / "results_summary.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
