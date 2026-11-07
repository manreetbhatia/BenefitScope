# Preliminary evaluation

Transactions are synthetic. Benefit rules and policy guides are real.

## Retrieval

| Setup | Hit rate | Context precision | Context recall |
| --- | ---: | ---: | ---: |
| Benefit-type filter only | 0.727 | 1.000 | 0.591 |
| Filter plus the neighboring page | 1.000 | 0.727 | 0.636 |

Hit rate is the share of benefit records for which search returned at least one page.
Context precision is the share of those pages that belong to the labeled benefit, or the page next to it. It is averaged only over searches that returned something.
Context recall is the share of published numbers from the benefit record - day window, delay hours, dollar cap - found in the retrieved text. A benefit with no retrieved page scores zero.

These benefits had no page tagged with that benefit type:

- Chase Sapphire Preferred return_protection
- American Express Platinum trip_delay_insurance
- Citi Strata Premier trip_delay_insurance

The chunker only labels a page when the benefit heading sits on its own line. Exclusions on the following page stay tagged `general`, and some benefits (notably American Express trip delay, which is not in the downloaded purchase/return PDFs) have no tagged page at all.

## Eligibility

| Slice | Count | Accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| All sampled purchases | 28 | 1.0 | 1.0 | 1.0 | 1.0 |
| Model was actually asked | 14 | 1.0 | 1.0 | 1.0 | 1.0 |
| purchase_protection | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| return_protection | 8 | 1.0 | 1.0 | 1.0 | 1.0 |
| trip_delay_insurance | 8 | 1.0 | 1.0 | 1.0 | 1.0 |

## Where it fails

Who made the decision on this sample: benefit_rule 1, hard_check 13, model 14.

On this sample, every eligible/not-eligible decision matched the label. That does not mean the search step is solid.

The real gap is retrieval. Three benefits have no page tagged with that benefit type, because the chunker only notices a benefit when its heading sits alone on a line. Chase return protection is in the Sapphire guide but was not tagged. American Express trip delay and Citi trip delay are not in the downloaded PDFs at all (the Amex files are purchase protection and return protection only). Neighboring-page search still returns some text for every benefit, but context precision falls to 0.727 because some of those pages are not actually about the benefit, and context recall stays at 0.636 because the published day limit, delay threshold, or dollar cap is often missing from the retrieved text.

The model also needs a guardrail. On an earlier run it rejected two theft claims for lacking damage photos. The benefit checklist does not require photos for theft, so that extra demand is now ignored. One later call (Chase return protection, txn_0013) was rejected by the model provider with HTTP 400, and the structured rule was used instead. The label still matched.

Hard rejections (wrong card, wrong event, late date, delay too short, unpaid purchase) never call the model, so they stay aligned with the benefit table. Citi has no return-protection record on purpose. A denied store return on that card is labeled not eligible.
