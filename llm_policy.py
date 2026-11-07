"""Use retrieved policy chunks to produce grounded, structured answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from retriever import PolicyRetriever


DEFAULT_MODEL = "openai/gpt-oss-20b"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
OUTPUT_DEFAULTS: dict[str, object] = {
    "answerable": False,
    "answer": "",
    "plain_language_answer": "",
    "issuer": None,
    "card_name": None,
    "benefit_type": None,
    "key_limits": [],
    "required_evidence": [],
    "exclusions": [],
    "citations": [],
    "disclaimer": "Verify the current guide to benefits before filing a claim.",
}


def load_api_key(path: Path) -> str:
    """Read either KEY=value dotenv format or a raw key from api.env."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, value = line.split("=", 1)
            if name.strip() in {"GROQ_API_KEY", "API_KEY"}:
                return value.strip().strip('"').strip("'")
        elif line.startswith("gsk_"):
            return line
    raise ValueError(f"No Groq API key found in {path}")


def build_prompt(question: str, evidence: list[dict[str, object]]) -> str:
    evidence_text = "\n\n".join(
        f"SOURCE {index}: {json.dumps({key: chunk[key] for key in ('issuer', 'card_name', 'benefit_type', 'document_title', 'page', 'source_url', 'text')})}"
        for index, chunk in enumerate(evidence, start=1)
    )
    return f"""You are a card-benefits policy assistant helping an ordinary card member.
Answer the user's question using only the supplied policy evidence.
Do not guess, combine unsupported terms, or use outside knowledge.
If the evidence is insufficient, set answerable to false and explain what is missing.
Write for a layperson: use simple everyday words, short sentences, and explain insurance terms.
Start both answer and plain_language_answer with the direct answer to the question.
State important numbers exactly as written in the evidence and explain what each limit means.
Do not call a maximum reimbursement amount a guaranteed payment.
Do not hide uncertainty, exceptions, exclusions, dates, or payment requirements.
Return valid JSON only with exactly these keys:
answerable (boolean), answer (string), plain_language_answer (string), issuer (string or null),
card_name (string or null), benefit_type (string or null), key_limits (array of strings),
required_evidence (array of strings), exclusions (array of strings),
citations (array of objects with document_title, page, source_url), disclaimer (string).

USER QUESTION:
{question}

POLICY EVIDENCE:
{evidence_text}
"""


def ask_llm(question: str, evidence: list[dict[str, object]], api_key: str, model: str) -> dict[str, object]:
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": build_prompt(question, evidence)},
        ],
    }
    request = Request(
        GROQ_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "card-benefit-activation-engine/0.1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 401:
            detail = "The Groq API key was rejected. Check that it is active and has not been revoked."
        elif error.code == 403:
            detail = (
                "Groq denied the request (403). If the response contains Cloudflare code 1010, "
                "try another network or use the official Groq SDK; also verify that the API key is active. "
                f"Provider detail: {detail}"
            )
        raise RuntimeError(f"Groq API request failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach Groq API: {error.reason}") from error

    content = response_body["choices"][0]["message"]["content"]
    model_result = json.loads(content)
    result = {**OUTPUT_DEFAULTS, **model_result}
    result["retrieved_chunks"] = [
        {
            "chunk_id": chunk["chunk_id"],
            "page": chunk["page"],
            "document_title": chunk["document_title"],
            "source_url": chunk["source_url"],
            "retrieval_score": chunk["score"],
        }
        for chunk in evidence
    ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--chunks", type=Path, default=Path("data/chunks.json"))
    parser.add_argument("--api-file", type=Path, default=Path("api.env"))
    parser.add_argument("--issuer")
    parser.add_argument("--benefit-type")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--json", action="store_true", help="Print the complete structured JSON response")
    args = parser.parse_args()

    retriever = PolicyRetriever(args.chunks)
    evidence = retriever.search(args.question, args.top_k, args.issuer, args.benefit_type)
    if not evidence:
        result = {
            **OUTPUT_DEFAULTS,
            "answer": "I could not find a matching policy section in the downloaded guides.",
            "plain_language_answer": "I could not find this information in the available policy documents.",
        }
        print(json.dumps(result, indent=2) if args.json else result["plain_language_answer"])
        return
    result = ask_llm(args.question, evidence, load_api_key(args.api_file), args.model)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(result["plain_language_answer"])
    if result["key_limits"]:
        print("\nImportant limits:")
        for limit in result["key_limits"]:
            print(f"- {limit}")
    if result["required_evidence"]:
        print("\nYou may need:")
        for item in result["required_evidence"]:
            print(f"- {item}")
    if result["citations"]:
        print("\nSource:")
        for citation in result["citations"]:
            print(f"- {citation['document_title']}, page {citation['page']}")
    print(f"\nNote: {result['disclaimer']}")


if __name__ == "__main__":
    main()
