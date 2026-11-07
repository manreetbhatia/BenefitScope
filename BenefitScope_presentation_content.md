# BenefitScope — Mid-term presentation content

**Full title:** BenefitScope: A Retrieval-Grounded System for Credit-Card Benefit Eligibility

**What this file is:** Slide-ready text for the mid-term talk. Each `##` heading is one slide. Paste the bullets into PowerPoint. Redraw the diagram on the framework slide; do not leave it as code.

**Scope to say out loud:** This is the mid-semester system, not the final project. Purchases are synthetic or typed by the user. The app is not connected to a bank.

---

## Slide 1 — Title

- BenefitScope: A Retrieval-Grounded System for Credit-Card Benefit Eligibility
- Mid-term evaluation
- Card Benefit Activation Engine
- Benefits covered: purchase protection, return protection, trip-delay insurance
- Cards in the rule table: Chase Sapphire Preferred, American Express Platinum, Citi Strata Premier, Capital One Venture X

Speaker line: We check whether a card’s own written guide covers a purchase. We do not approve a real claim and we do not see a live card swipe.

---

## Slide 2 — Introduction

- Card guides are long, and the numbers differ by issuer.
- A holder often does not know if theft, a refused return, or a delayed flight is covered.
- BenefitScope does three jobs:
  1. Stores the real numeric rules (window, cap, delay hours, documents).
  2. Searches 13 downloaded benefit-guide PDFs and quotes the page.
  3. Decides eligible or not eligible, and refuses to invent a dollar amount.
- A person signs up, picks the cards they use, and sees a purchase list with date, card, item, and store.
- Plain-language questions (“I want to buy a Sony TV from xyz store”) are answered from the PDFs, not from a fixed paragraph.

---

## Slide 3 — Motivation: Issues and Challenges

- The same event is covered differently on different cards.
  - Chase Sapphire Preferred purchase protection: 120 days, up to $500 per item.
  - American Express Platinum purchase protection: 90 days, up to $10,000 per claim.
  - Chase trip delay starts at 12 hours. Amex Platinum, Citi, and Venture X start at 6 hours.
- Citi Strata Premier has no return protection. A system that “fills in” a return rule would be wrong.
- Guides are PDFs. The cap is often on a different page from the heading.
- A language model will state a confident limit even when the page does not say it.
- There is no public benchmark of purchase-protection, return-protection, and trip-delay eligibility.
- A live bank feed is out of scope for this mid-term. History must still be tied to one person and to the cards that person selected.

---

## Slide 4 — Literature Review

Say this before the table: these papers solve related problems. None of them is a card-benefit eligibility benchmark, so their scores are not compared as if they were our accuracy.

| Work | Technique | Data | What they measure | What it does not give us |
| --- | --- | --- | --- | --- |
| Lewis et al., NeurIPS 2020 (RAG) | Retrieve passages, then generate | Wikipedia, open-domain QA | Exact match / F1 on knowledge questions | No card, no coverage window, no claim decision |
| Karpukhin et al., EMNLP 2020 (DPR) | Dense vector retrieval | Wikipedia passages | Recall of the gold passage | Needs embeddings and training pairs; we stayed with TF-IDF |
| Robertson and Zaragoza, 2009 (BM25) | Sparse word matching | Standard IR collections | Ranking quality | Same family as our search; not a benefit checker |
| Chen et al., EMNLP 2021 (FinQA) | Numerical reasoning over tables and text | Financial reports | Execution accuracy on finance questions | Earnings reports, not guide-to-benefits PDFs |
| Es et al., RAGAS, 2023 | Score retrieval and faithfulness | RAG outputs | Context precision, context recall, faithfulness | We use the same idea of precision and recall, computed against our labeled rules, not with an LLM judge |

Gap to say in one sentence: prior work retrieves or answers, but it does not force an issuer-specific rule (days, hours, dollars) to agree with a cited guide page before a yes or no.

---

## Slide 5 — Problem Definition

- Input: one purchase and one event.
  - Card issuer and card name, category, amount, purchase date.
  - Event: theft, damage, store return denied, flight delay, or none.
  - Evidence on file, such as a receipt or a police report.
- Output: eligible or not, the benefit type, a confidence, the cited sentence, the document and page, and any missing document.
- Hard cases that must be rejected without guessing:
  - Wrong card, wrong category, day 121 of a 120-day window, a 5-hour delay when the rule requires 6, a card that does not offer the benefit.
- The amount may be above the cap. That is still a possible partial reimbursement, not an automatic no.
- A second input is a shopping sentence before any loss happens. The output is the matching guide quote for purchase protection and return protection, plus a next-purchase discount only if a page states one.
- Constraint: every number on the shopping screen must appear in the quoted PDF. If the page has no number, we do not copy one from the rule file.

---

## Slide 6 — Objectives

Mid-term objectives (done):

1. Encode 11 real benefit rules for the four cards, including the fact that Citi has no return protection.
2. Download and index issuer PDFs so an answer can point at a page.
3. Label 400 synthetic purchases from the rules, with boundary cases.
4. Reject impossible claims with a deterministic filter before calling a model.
5. Ask the model only when the filter still allows a benefit, and keep the model from inventing figures.
6. Measure retrieval and eligibility on a held-out sample.
7. Provide a signed-in screen: purchase history for that user’s cards, and a plain-language lookup over the PDFs.

Left for the rest of the semester (not claimed as done):

- Put the extra PDF cards (Sapphire Reserve, United Club, Freedom, and others) into the rule table without inventing numbers.
- Add official rewards or offer documents if a next-purchase discount is to be shown.
- Compare TF-IDF with a denser retriever on a larger test set.

---

## Slide 7 — Proposed System (say this, then show the diagram)

Five stages. Stages 1–3 do not call the model.

1. **Account.** The user signs up with a username and password. The password is stored as a salted hash. The user selects the cards they hold.
2. **History.** The account shows date, card, item, store, and amount. Starter rows are sample charges for those cards. Rows the user types are stored only on that account.
3. **Hard filter.** Same issuer and card, event matches the benefit, category is allowed, date or delay is inside the rule, and the card was actually charged. Fail here and stop.
4. **PDF search.** TF-IDF ranks pages from the 13 guides. The claim checker also pulls the neighboring page, because exclusions often sit there.
5. **Grounded decision.** The model sees the purchase, the structured rule, and a short quote. Missing documents that the checklist does not require cannot flip a yes to a no. If the model call fails, the structured rule is used and marked as such.

Shopping path (separate from a claim): the sentence is searched for purchase protection, return protection, and any sentence that actually says discount, statement credit, or next purchase. No such discount sentence is in the current guides, so the screen says so.

---

## Slide 8 — Block diagram (redraw this in PowerPoint)

```text
[ Sign up / log in ]
        |
        v
[ Cards on this account ] ----> [ My purchases: date, card, item, store, amount ]
        |
        +---------------------------+
        |                           |
        v                           v
[ Shopping sentence ]        [ Claim: purchase + event ]
        |                           |
        v                           v
[ TF-IDF over 13 PDFs ]      [ Hard filter on the 11 rules ]
        |                           |
        |                     fail  |  pass
        |                      |    |
        |                      v    v
        |               [ Not eligible ]  [ Retrieve guide pages ]
        |                                      |
        |                                      v
        |                               [ Groq model, JSON ]
        |                                      |
        v                                      v
[ Quote + page, or            [ Eligible? + citation + missing documents ]
  "no discount stated" ]
```

Boxes to label under the diagram:

- Rules file: `benefits_data.json` (11 records).
- Guides: `sources.json` → PDFs → `data/chunks.json`.
- People: `data/users.json` (hash only).
- Sample claims: `data/transactions.json` (400 rows).

---

## Slide 9 — How one claim is decided (flow)

1. Map the event: theft or damage → purchase protection; refused return → return protection; flight delay → trip delay; none → stop.
2. If this card has no such benefit, stop. Example: Citi and a refused return.
3. Check category, exclusions, window or delay hours, and payment on the card.
4. If any hard check fails, return not eligible. Do not call the model.
5. Search the PDFs for that issuer and benefit. Keep a short quote.
6. Ask the model for JSON: eligible, benefit, confidence, cited sentence, source, missing documents.
7. If required evidence is missing, force not eligible.
8. If the model demands a photo or police report that this event does not need, keep the rule.

---

## Slide 10 — What a shopping question returns

Example sentence: “I want to buy a Sony TV 65 inches from xyz store.”

- Read as an electronics purchase at that store. The guides do not name Sony or the store.
- Purchase protection: a quoted page (in the demo, American Express Platinum guide, page 3).
- Return protection: a quoted page (in the demo, Chase United Club guide, page 18, 90-day refused-return wording).
- Next purchase: none of the uploaded guides state a discount on the next purchase.
- Other hits can include extended warranty, because that heading is in the same PDFs.
- Choosing one card limits the quotes to that card. Citi has no return-protection page in the indexed guides, so that block says the page is not there.

---

## Slide 11 — Experimental setup

- Language: Python.
- PDF text: pypdf. Some Chase files needed the cryptography package.
- Search: TF-IDF and cosine similarity written in the project. Not an embedding index.
- Model: Groq, `openai/gpt-oss-20b`, temperature 0, JSON output. Calls spaced about 8 seconds apart because of the token limit.
- Rules under test: 11 benefit records.
- Labeled purchases: 400, about half eligible.
- Eligibility sample: 28 purchases, stratified across benefit type and the yes/no label. This is a preliminary sample, not a full test set.
- Retrieval sample: the same 11 rules, searched with and without the neighboring page.
- No neural network was trained. There is no training-loss curve. The label is computed from the rules, and the model is used zero-shot.

---

## Slide 12 — Experimental results

**Eligibility (28 purchases)**

| Slice | Count | Accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| All sampled purchases | 28 | 1.0 | 1.0 | 1.0 | 1.0 |
| Model was actually asked | 14 | 1.0 | 1.0 | 1.0 | 1.0 |
| Purchase protection | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| Return protection | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| Trip-delay insurance | 8 | 1.0 | 1.0 | 1.0 | 1.0 |

Who decided: hard filter 13, model 14, structured rule after a failed model call 1.

Confusion matrix on this sample: false positives 0, false negatives 0.

**Retrieval (11 benefit records)**

| Setup | Hit rate | Context precision | Context recall |
| --- | ---: | ---: | ---: |
| Benefit-type filter only | 0.727 | 1.000 | 0.591 |
| Filter plus the next page | 1.000 | 0.727 | 0.636 |

Hit rate: share of benefits for which at least one page came back.
Context precision: share of those pages that match the benefit, or the next page.
Context recall: share of the published numbers (days, hours, dollar cap) found in the retrieved text.

---

## Slide 13 — Discussion (do not hide this)

- A perfect eligibility score on 28 rows does not mean search is solved. Thirteen of the 28 decisions never called the model, because the hard filter already knew the answer.
- On an earlier run the model rejected two theft claims for lack of damage photos. The checklist does not require photos for theft. That extra demand is now blocked.
- One Chase return-protection call failed at the provider (HTTP 400). The structured rule was used. The label still matched.
- Retrieval misses when the benefit heading is not on its own line. In the recorded run, Chase Sapphire Preferred return protection, Amex Platinum trip delay, and Citi trip delay had no page tagged with that benefit type. Adding the next page raises hit rate to 1.0 and drops precision to 0.727.
- More PDFs were added after that score file was written, including Amex trip-delay guides. Those 13-file pages are what the app searches now. The table on the previous slide is the recorded mid-term score, not a rescore of the final corpus.
- The guides do not state a percent off the next purchase. Showing one would be a fabricated benefit.

---

## Slide 14 — Plan of action after the mid-term

1. Rescore retrieval on the current 13-PDF index and publish the new table.
2. Add structured rules only where a downloaded guide states the number. Do not guess Sapphire Reserve or United Club caps.
3. If next-purchase offers are required, register separate official offer or rewards PDFs and search those. Keep the “not stated” message until a page says it.
4. Compare TF-IDF with BM25, then with a dense retriever, on the same 11 questions.
5. Grow the eligibility sample beyond 28 and break errors down by benefit, not only by a single F1.
6. Send a purchase the user typed through the same hard filter and citation path, so history and eligibility use one record.
7. Tighten citations so the quoted line is the guide sentence, not a field name from the rule file.

---

## Slide 15 — Conclusion and Future Directions

- BenefitScope is a mid-term prototype that ties one person, their cards, a purchase list, and a cited guide page.
- Eligibility on the 28-purchase sample matched the rule label in every case.
- The open weakness is retrieval: finding the page is not the same as finding the sentence that states the cap.
- The system is honest where a benefit is absent (Citi return protection, and any next-purchase discount).
- It is not a claims department and not a bank connection.
- The rest of the semester is a fairer retrieval comparison, a larger sample, rules only from pages we can quote, and a path from a typed purchase to a cited decision.

---

## Backup slide — Tools (if asked)

- Python, pypdf, cryptography
- TF-IDF retriever written in the project
- Groq chat API, model openai/gpt-oss-20b
- FastAPI for `POST /check-eligibility` and `POST /lookup-purchase`
- Streamlit for the screens
- Password hashing: PBKDF2-SHA256 with a random salt
- Local files only: rules, chunks, transactions, users
