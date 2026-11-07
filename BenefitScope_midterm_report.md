# BenefitScope: A Retrieval-Grounded System for Credit-Card Benefit Eligibility

**Mid-term report.** This is the work completed by the mid-semester review. It is not the final system.

---

## Abstract

Credit-card protection rules are buried in long guides, and the numbers change with the issuer. A theft that is inside a 120-day window on one card can be outside a 90-day window on another, and a delayed flight can be covered only after six hours or only after twelve. This mid-term project, BenefitScope, checks purchase protection, return protection, and trip-delay insurance for four cards: Chase Sapphire Preferred, American Express Platinum, Citi Strata Premier, and Capital One Venture X. Eleven rules were taken from issuer materials. Thirteen benefit-guide PDFs were downloaded and indexed with TF-IDF. Four hundred synthetic purchases were labeled from those rules, including boundary cases such as the last covered day and a delay one hour too short. A deterministic filter rejects claims that fail the card, category, date, delay, or payment test. Only the claims that survive are sent to a language model with a short guide quote. The model must cite the page and may not invent a dollar limit. On a stratified sample of 28 purchases, eligibility precision, recall, and F1 were all 1.0. Retrieval was weaker: with a benefit-type filter, hit rate was 0.727 and context recall of the published numbers was 0.591. A signed-in screen lists purchases on the cards that person selected and answers a shopping sentence from the PDFs. The current guides do not state a discount on the next purchase, and the screen says so. BenefitScope is a grounded prototype, not a live link to a bank.

---

## Impact Statement

Cardholders miss valid protection claims, and they also file claims a card does not offer. BenefitScope shows the written rule and a guide page before a claim starts. On a sample of 28 labeled purchases, the yes-or-no decision matched the rule every time. Thirteen of those decisions were hard rejections, so the model was not asked to guess. The result is a cited page, or a plain reason such as a late date, a short delay, or a missing benefit. Citi Strata Premier is reported as having no return protection, not a guessed policy. The screen can also answer a planned purchase from the uploaded guides. It is not a production claims desk: purchases are synthetic or typed by the user, search still misses some published caps, and no next-purchase discount is stated in the guides.

---

## Index Terms

benefit eligibility, credit-card guides, large language models, purchase protection, retrieval-augmented generation, TF-IDF

---

## I. Introduction

A guide to benefits is the contract behind purchase protection, return protection, and trip-delay insurance. Holders do not read it at the moment of a loss. The figures that matter — how many days, how many hours, how many dollars — are easy to confuse across Chase, American Express, Citi, and Capital One. A chatbot that answers from memory can sound sure and still be wrong. BenefitScope is a mid-semester system that keeps those figures tied to a stored rule and to a page in a downloaded guide.

The system has two questions. The first is a claim question: given a purchase and an event, is this card’s benefit available? The second is a shopping question: given a sentence such as “I want to buy a Sony TV from xyz store,” which protection pages apply, and does any uploaded page state a discount on a later purchase? Both questions are answered for a signed-in person, and the purchase list shows the date, the card, the item, and the store.

### A. Contributions

The major contributions of this mid-term work are the following.

1. A rule layer for eleven benefits on four cards, including an explicit absence: Citi Strata Premier has purchase protection and trip-delay insurance and does not have return protection. Labels for synthetic purchases are computed from this layer, not assigned by hand.
2. A document layer: thirteen issuer PDFs are registered, downloaded, split into pages, and searched with TF-IDF. A claim or a shopping question returns the document title, page, and a quote.
3. A decision layer: hard checks run first. The language model is called only when a benefit is still possible. Missing documents are computed in code. A model demand for a document the checklist does not require does not override the rule.
4. A person layer: signup and login, a salted password hash, and a purchase history limited to the cards selected for that account.
5. A preliminary evaluation: retrieval hit rate, context precision, and context recall on the eleven rules, and eligibility precision, recall, and F1 on 28 labeled purchases.

The remainder of this report is organized as follows. Section II states why the problem is difficult. Section III reviews related retrieval and financial-document work and the gap those papers leave. Section IV defines the decision problem. Section V explains the system, with a block diagram and the decision procedure. Section VI reports the mid-term measurements and their limits.

---

## II. Motivation

Three protections look similar and are not.

Purchase protection pays after theft or damage inside a window that starts on the purchase date. On the rules used here, Chase Sapphire Preferred allows 120 days and up to $500 per item. American Express Platinum, Citi Strata Premier, and Capital One Venture X allow 90 days, with a much higher per-claim cap on the materials we encoded ($10,000). Return protection pays when the store will not take an undamaged item back. Chase Sapphire Preferred and Capital One Venture X use 90 days; the per-item caps in our rule table are $500 and $300. Trip-delay insurance pays expenses after a common-carrier delay. Chase Sapphire Preferred requires 12 hours. American Express Platinum, Citi Strata Premier, and Capital One Venture X require 6 hours, with a $500 cap in the rule table.

Two failures follow from that table. A holder can miss a real claim, or a system can invent a claim the card does not sell. Citi is the clear case of the second failure: return protection is absent, not merely missing from our file by accident. A third failure is numeric. If the retrieved page does not contain “$500” or “twelve (12) hours,” a fluent model will often supply a number anyway.

Search has its own difficulty. Benefit headings are not always on a line by themselves, so a page can stay tagged as general. Exclusions often continue on the next page. The recorded retrieval run found no page tagged as Chase Sapphire Preferred return protection, American Express Platinum trip delay, or Citi trip delay. Neighboring-page search still returns text, but some of that text is the wrong section.

The mid-term also had to be about a person, not a shared spreadsheet. A class demo that shows all 400 sample rows to every visitor does not answer “what did this cardholder buy, on which card, and on which date?” Signup, a card list, and a per-account history answer that question inside the prototype. They do not connect to a bank.

### A. Why this is only a mid-term

The eligibility score below is on 28 purchases. Thirteen of those decisions never reached the model. The retrieval table was computed before the corpus grew to the thirteen PDFs now on disk, including later Amex trip-delay guides. Those limits are stated again in Section VI so the score is not read as a finished benchmark.

---

## III. Literature Work

BenefitScope sits next to retrieval-augmented generation, sparse search, and question answering over financial documents. It is not a new language model, and it is not a claim-payment network.

Lewis et al. introduced retrieval-augmented generation: a retriever fetches passages and a generator conditions on them instead of relying only on parameters [1]. That design is why our claim prompt includes guide text. Their experiments are open-domain questions over Wikipedia, not coverage windows or card names. Karpukhin et al. showed that a trained dense retriever can recall the passage that contains the answer [2]. We did not train a dense index. The mid-term retriever is TF-IDF, in the same sparse family as BM25, the ranking function surveyed by Robertson and Zaragoza [3]. Sparse matching is a reasonable first tool when the query contains a rare phrase such as “return protection” or “trip delay.”

Chen et al. built FinQA for numerical reasoning over financial reports [4]. That work matters because a wrong number is a wrong answer. Their documents are earnings filings and tables, not a guide to benefits, so their execution accuracy is not a score we can place next to ours. Es et al. proposed RAGAS to score context precision, context recall, and faithfulness of retrieval-augmented answers [5]. Our evaluation uses context precision and context recall in that spirit. We compute them by checking labeled benefit pages and published numbers. We do not call an LLM as the judge.

### A. Comparison of related work

| Reference | Technique used | Database used | Accuracy / measures | Remarks |
| --- | --- | --- | --- | --- |
| Lewis et al., 2020 [1] | Retrieve passages, then generate | Wikipedia; open-domain QA sets | Exact match and F1 on knowledge questions (a different task) | Shows that retrieved text reduces reliance on model memory. Does not decide card eligibility or enforce a coverage cap. |
| Karpukhin et al., 2020 [2] | Dense dual-encoder retrieval | Wikipedia passages | Passage recall at a cutoff (a different task) | Strong when many labeled questions exist. Our mid-term system does not embed pages. |
| Robertson and Zaragoza, 2009 [3] | BM25 sparse ranking | Standard information-retrieval collections | Ranking quality on those collections | Same idea as our TF-IDF: overlap of words. Not a benefit classifier. |
| Chen et al., 2021 [4] | Numerical reasoning over text and tables | FinQA financial reports | Execution accuracy on finance questions (a different task) | Motivates checking every dollar figure. The documents are not card guides. |
| Es et al., 2023 [5] | Reference-based and judge-based RAG scores | RAG system outputs | Context precision, context recall, faithfulness | We report precision and recall of retrieved pages and of published numbers. We do not use their LLM judge. |
| This mid-term system | Rules, then TF-IDF, then a grounded model call | 11 benefit rules; 13 guide PDFs; 400 synthetic purchases | Eligibility F1 1.0 on 28 purchases; retrieval hit rate 0.727 (filter only) and 1.0 (with the next page) | Small sample. Perfect F1 is not a retrieval success. See Section VI. |

No public dataset known to us labels purchase protection, return protection, and trip delay on these four cards with page-level citations. That is why the purchases in this project are synthetic and why their labels are derived from the rule file.

### B. Gap, issues, and challenges

From the table, four gaps define this minor project.

1. **No shared task.** Open-domain QA and FinQA do not ask whether a specific card covers a theft on day 121 or a delay of five hours.
2. **Numbers must be grounded.** A fluent answer that states the wrong cap is worse than a refusal. The system needs a rule for the number and a page that can be opened.
3. **Absence is an answer.** If a product has no return protection, the correct output is that absence. Literature systems that always return a passage will still “find” a nearby paragraph.
4. **The person is missing.** Retrieval papers do not store who holds which card, or what that person bought on which date. A demo of benefits that is not tied to an account cannot show a purchase history.

The practical challenges follow: PDF headings that do not fall on their own line, exclusions on the next page, a model that asks for documents the checklist does not require, and a token limit that rejects long prompts. None of these are solved by citing a higher score from a different dataset.

---

## IV. Problem Definition

Let a purchase be `x = (issuer, card, category, amount, date, event, evidence)`. The event is theft, damage, a refused return, a flight delay with a length in hours, or none. Benefit `b` is purchase protection, return protection, trip delay, or none. The task is `f(x) = (eligible, b, confidence, quote, source, missing)`, where `source` is a title, a page, and a URL.

`H(x, b)` fails if the benefit is for another card, the event does not match `b`, the category is outside the rule, the amount is not positive, the date is past the window, the delay is too short, or the card-payment rule is missed. A price above the cap does not fail `H`, because part of the price can still be reimbursed. If `H` fails, `f` returns not eligible and does not call a model. If the card has no such benefit, that absence is the reason. If `H` passes, the model may answer only from the retrieved pages and the stored rule. Missing required documents force eligible to no.

`g(sentence, cards)` returns protection quotes and a next-purchase quote. The discount list stays empty unless the page itself states a discount, a statement credit, or a next purchase. A user `u` holds cards `C(u)`, and the history of `u` shows only those cards, with date, item, and store. We do not train `f`. `H` is the rule table, search is TF-IDF, and the model only reads pages `H` has allowed.

---

## V. Proposed Framework

### A. Block diagram

```text
                         +------------------+
                         |  Sign up / login |
                         |  salted password |
                         +--------+---------+
                                  |
                                  v
                    +-------------+--------------+
                    | Cards selected for this    |
                    | account                    |
                    +-------------+--------------+
                                  |
              +-------------------+-------------------+
              |                                       |
              v                                       v
   +-----------------------+               +----------------------+
   | Purchase history      |               | New question         |
   | date, card, item,     |               | shopping sentence    |
   | store, amount         |               | or claim event       |
   +-----------------------+               +----------+-----------+
                                                      |
                         +----------------------------+----------------------------+
                         |                                                         |
                         v                                                         v
              +--------------------+                                  +------------------------+
              | Shopping search    |                                  | Hard filter H          |
              | TF-IDF on 13 PDFs  |                                  | 11 structured rules    |
              +----------+---------+                                  +-----------+------------+
                         |                                                        |
                         |                                              fail      |      pass
                         |                                                |       |        |
                         v                                                v       |        v
              +--------------------+                           +--------------+  |  +------------------+
              | Quoted pages       |                           | Not eligible |  |  | Retrieve pages   |
              | or "not stated"    |                           | (no model)   |  |  | + neighbor page  |
              +--------------------+                           +--------------+  |  +--------+---------+
                                                                                 |           |
                                                                                 |           v
                                                                                 |  +--------+---------+
                                                                                 |  | Grounded model   |
                                                                                 |  | JSON + checklist |
                                                                                 |  +--------+---------+
                                                                                 |           |
                                                                                 |           v
                                                                                 |  +--------+---------+
                                                                                 +->| Eligible? quote, |
                                                                                    | page, missing    |
                                                                                    | documents        |
                                                                                    +------------------+
```

Data files under the diagram:

| File | Role |
| --- | --- |
| `benefits_data.json` | Eleven rules: window or hours, caps, categories, exclusions, documents, payment rule, source note |
| `sources.json` | Thirteen guide records and URLs |
| `data/chunks.json` | Pages extracted from those PDFs, with issuer, card, and benefit tag when the heading is recognized |
| `data/transactions.json` | Four hundred synthetic labeled purchases |
| `data/users.json` | Accounts. Passwords are salted PBKDF2-SHA256 hashes, not plain text |

### B. Processing steps

**Step 1 — Guides.** Each source is downloaded. A file that is not a PDF is skipped. Each page is read with pypdf. If a line is exactly a known heading (purchase protection, purchase security, damage and theft, return protection, trip delay, trip delay insurance, trip delay reimbursement), the following text is tagged with that benefit. Other text stays `general`.

**Step 2 — Rules and labels.** The same rule functions label the synthetic set and run the live filter. The event map is fixed: theft and damage map to purchase protection, a refused return maps to return protection, a flight delay maps to trip delay, and “none” maps to no benefit. About half of the 400 purchases are eligible. Boundary rows include day 120 versus day 121 and a delay on the threshold versus one hour below it.

**Step 3 — Account.** Signup asks for a name, a username, a password of at least six characters, and at least one card. The starter history copies up to six distinct sample purchases for each selected card (distinct store, date, category, and amount). The user can add a row: item, store, amount, date, and one of their cards. That row is marked as entered and is not copied to any other account.

**Step 4 — Claim filter.** `H` checks card identity, event type, category, exclusions, positive amount, window or delay, and payment. Conditional evidence is applied only when it matches the event: a police report for theft, photos for damage. Items marked “if applicable” are not required by default.

**Step 5 — Retrieval.** Query tokens are weighted with TF-IDF. Pages are ranked by cosine similarity. The search can be limited by issuer and by benefit tag. For a claim, the next page is also kept, because exclusions often continue there. For a shopping sentence, three searches run: purchase protection, return protection, and the raw sentence (plus a topic query such as trip delay when the sentence is about a flight). Hits under a small score floor are dropped.

**Step 6 — Model read.** The prompt contains the purchase, the structured numbers, and at most three short quotes. Temperature is 0. The reply must be JSON. Calls are spaced by about eight seconds. If the provider returns “try again,” the call is retried. If required evidence is missing, the code sets eligible to no. If the model’s reason demands photos, a police report, or a receipt that the checklist does not list as missing, the rule stands. The decision source is recorded as model, hard check, or benefit rule.

**Step 7 — Shopping guard.** A next-purchase hit is kept only when the quote contains a discount, a statement credit, a next purchase, or a percent off. Word overlap alone is not enough, because “purchase” also appears on warranty pages.

### C. Procedure for one claim

```text
function DECIDE(x, rules, index):
    b ← benefit type of x.event
    if b is none:
        return not eligible, source = hard check
    rule ← the record in rules for x.card and b
    if rule does not exist:
        return not eligible, "this card does not offer b"
    if H(x, rule) fails:
        return not eligible, with the failed check, source = hard check
    pages ← SEARCH(index, x, rule) plus the neighbor page
    reply ← MODEL(x, rule, pages)     # JSON, temperature 0
    if reply failed:
        return the rule's own yes/no, source = benefit rule
    missing ← documents the checklist requires and x does not have
    if missing is not empty:
        reply.eligible ← no
    if reply rejects only because of a document that is not in missing:
        restore the rule's decision
        source ← benefit rule
    return reply, with quote, page, and URL
```

### D. What the screens show

After login the first tab is **My purchases**: date, card, what was bought, store, and amount. **Ask about a purchase** runs the shopping search on the user’s cards. **Check a purchase** runs `DECIDE` on a sample claim. **Sample purchases** is the full labeled set of 400, separate from the user’s list. **Benefit rules** shows the eleven records. **Search the guides** is TF-IDF without a claim decision. **Source documents** lists the thirteen guides.

The HTTP API exposes the same two operations: check one claim, and look up one shopping sentence.

---

## VI. Experimental Results and Discussion

### A. Model setting and protocol

| Item | Setting |
| --- | --- |
| Language | Python |
| PDF extraction | pypdf; cryptography for encrypted Chase files |
| Retriever | In-project TF-IDF and cosine similarity. No embedding model. No FAISS index. |
| Reader model | Groq, `openai/gpt-oss-20b`, temperature 0, JSON object |
| Call spacing | About 8 seconds, with retries when the provider asks for a wait |
| Prompt size | At most three chunks, each truncated, to stay inside the token limit |
| Rules | 11 benefit records on 4 cards |
| Corpus at scoring time | Pages available for that recorded run |
| Corpus in the app now | 13 registered PDFs. Retrieval was not fully re-scored after the later Amex trip-delay files were tagged. |
| Labeled pool | 400 synthetic purchases |
| Eligibility sample | 28, stratified by benefit type and by the yes/no label |
| Split | There is no training set. The model is not fine-tuned. |
| What “label” means | Computed by the same rule code as the filter. It is not a human rater and not a bank decision. |

Because nothing was trained, this section does not report a training curve or a validation curve. Those plots apply to a fitted classifier. Here the fitted part is the rule table, which is exact on the cases it encodes, and the measured parts are retrieval and the zero-shot reader.

### B. Evaluation measures

For eligibility, on the 28 purchases:

- Accuracy: share of rows where predicted yes/no equals the label.
- Precision: among predicted eligible rows, the share that are labeled eligible.
- Recall: among labeled eligible rows, the share predicted eligible.
- F1: the harmonic mean of precision and recall.
- A separate score on the 14 rows where the model was actually called, so fallbacks to the rule are not counted as model skill.

For retrieval, on the 11 rules:

- Hit rate: share of benefits for which search returned at least one page.
- Context precision: share of returned pages that match the labeled benefit or the next page, averaged only over queries that returned something.
- Context recall: share of published numbers (window days, “N hours,” dollar cap) found in the retrieved text. A benefit with no page scores zero.

### C. Eligibility results

| Slice | Count | Accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| All sampled purchases | 28 | 1.0 | 1.0 | 1.0 | 1.0 |
| Model was actually asked | 14 | 1.0 | 1.0 | 1.0 | 1.0 |
| Purchase protection | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| Return protection | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| Trip-delay insurance | 8 | 1.0 | 1.0 | 1.0 | 1.0 |

Decision source on the 28: hard check 13, model 14, benefit rule 1. The single benefit-rule case was a Chase return-protection call that the provider rejected with HTTP 400. The structured rule was used, and it matched the label.

Confusion matrix for eligible versus not eligible on these 28 rows:

|  | Predicted eligible | Predicted not eligible |
| --- | ---: | ---: |
| Labeled eligible | all labeled-eligible rows | 0 |
| Labeled not eligible | 0 | all labeled-not-eligible rows |

False positives are 0 and false negatives are 0 on this sample. The matrix is diagonal. That statement is only as strong as a 28-row preliminary sample.

### D. Retrieval results

| Setup | Hit rate | Context precision | Context recall |
| --- | ---: | ---: | ---: |
| Benefit-type filter only | 0.727 | 1.000 | 0.591 |
| Filter plus the neighboring page | 1.000 | 0.727 | 0.636 |

In that recorded run, three benefits had no page tagged with their type: Chase Sapphire Preferred return protection, American Express Platinum trip-delay insurance, and Citi Strata Premier trip-delay insurance. Chase return protection is in the Sapphire guide but was not tagged, because the chunker only fires when the heading is its own line. Adding the next page lifts hit rate to 1.0 and lowers precision to 0.727, which means some extra pages are not about that benefit. Context recall stays near 0.6 because the day limit, the hour threshold, or the dollar cap is often missing from the text that was retrieved.

The app’s later corpus includes additional guides, among them American Express trip-delay PDFs that can now be tagged. The table above was not regenerated after that ingest. For the mid-term we report the recorded numbers and do not replace them with an unscored claim about the new files.

### E. Discussion

The eligibility result is real on this sample and easy to over-read. Almost half of the rows (13 of 28) were decided by the hard filter. Those rows test the rule code, which is also the code that wrote the labels, so agreement there is expected. The informative rows are the 14 that reached the model. They also matched, after two guards were added.

On an earlier paced run, the model rejected two theft claims because damage photos were not attached. The checklist requires photos for damage, not for theft. The prompt now says so, and a rejection that rests only on that extra document is overridden. The guard was kept narrow so that a genuine “insufficient evidence” reason is not wiped out.

Citations are still uneven. Some answers quote a sentence from the PDF. Others have quoted a field name from the rule JSON and a marketing URL. That is a failure of the reader step even when yes/no is correct. It is listed as remaining work, not as a solved citation problem.

Shopping search behaves differently from the claim score. A television sentence and a flight sentence cite different pages. A flight sentence brings trip-delay pages into the other-pages group. A next-purchase query on the current guides returns no offer. That empty result is the correct mid-term behavior.

Account behavior was checked with unit tests: a signup copies sample rows only for the selected cards, a wrong password does not log in, and a purchase typed on one account does not appear on another. The browser signup path showed six Chase Sapphire Preferred rows with date, card, item, store, and amount.

### F. Threats to validity

- Labels and the filter share one implementation. They cannot disagree on a hard check unless one of them has a bug. The model-asked slice is the fairer test, and it is only 14 rows.
- Synthetic merchants and amounts are not a cardholder’s real statement.
- The Citi guide in the registry is a third-party copy, flagged that way in the source list. It should be replaced with an official file before any real use.
- Retrieval metrics and the live 13-PDF index are not from the same frozen snapshot.
- No user study was run. We did not measure whether a holder would trust or understand the quote.

---

## References

[1] P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, W. Yih, T. Rocktäschel, S. Riedel, and D. Kiela, “Retrieval-augmented generation for knowledge-intensive NLP tasks,” in *Advances in Neural Information Processing Systems*, 2020.

[2] V. Karpukhin, B. Oğuz, S. Min, P. Lewis, L. Wu, S. Edunov, D. Chen, and W. Yih, “Dense passage retrieval for open-domain question answering,” in *Proc. EMNLP*, 2020.

[3] S. Robertson and H. Zaragoza, “The probabilistic relevance framework: BM25 and beyond,” *Foundations and Trends in Information Retrieval*, vol. 3, no. 4, pp. 333–389, 2009.

[4] Z. Chen, W. Chen, C. Smiley, S. Shah, I. Borova, D. Langdon, R. Moussa, M. Beane, T.-H. Huang, B. Routledge, and W. Y. Wang, “FinQA: A dataset of numerical reasoning over financial data,” in *Proc. EMNLP*, 2021.

[5] S. Es, J. James, L. Espinosa-Anke, and S. Schockaert, “RAGAS: Automated evaluation of retrieval augmented generation,” arXiv:2309.15217, 2023.

---

## Note for the Word file

Copy the abstract, impact statement, index terms, and Sections I–VI into the IEEE or department template. Do not paste this note. Redraw the Section V diagram in Word (Insert → Shapes). The abstract and the impact statement were written to the word limits in the assignment: the abstract is under 250 words and the impact statement is under 150 words. Confirm the counts in Word after you paste, because Word and this file can count hyphenated terms differently.
