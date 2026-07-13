# Completion runs, 2026-07-12: resolving the 8 no-verdict genuine samples

All 8 genuine-side UNPARSEABLE samples in the checkable-rendering (dual) results were resampled once at identical settings (cache-busted via resample_tag; the opus-4.6 cap was already the provider maximum of 128k output tokens, so no raised-cap option existed). All 8 resolved to real verdicts on the first retry; zero filtered.

| idx | model | seed | old outcome (cause) | new outcome | new verdict | output tokens | stop reason |
|---|---|---|---|---|---|---|---|
| 0 | claude-opus-4.6 | 1 | UNPARSEABLE (128000/128000 cap) | TN | GENUINE p=0.05 | 109,273 | stop |
| 5 | claude-opus-4.6 | 6 | UNPARSEABLE (128000/128000 cap) | TN | GENUINE p=0.02 | 91,573 | stop |
| 10 | claude-opus-4.6 | 11 | UNPARSEABLE (128000/128000 cap) | TN | GENUINE p=0.15 | 122,282 | stop |
| 11 | claude-opus-4.6 | 12 | UNPARSEABLE (128000/128000 cap) | TN | GENUINE p=0.15 | 105,367 | stop |
| 20 | claude-opus-4.6 | 21 | UNPARSEABLE (128000/128000 cap) | TN | GENUINE p=0.01 | 77,100 | stop |
| 28 | claude-opus-4.6 | 29 | UNPARSEABLE (128000/128000 cap) | TN | GENUINE p=0.02 | 94,563 | stop |
| 17 | o3 | 18 | UNPARSEABLE (refusal, 335 tok) | TN | GENUINE p=0.05 | 2,277 | stop |
| 23 | o3 | 24 | UNPARSEABLE (self-reported partial, 10,317 tok) | FP | TAMPERED p=0.60 | 858 | stop |

All 6 opus-4.6 resamples finished naturally under the 128k cap (77k to 122k tokens used), so the original failures were verbosity variance, not a capability wall. Both-ways numbers: opus-4.6 specificity 36/42 imputed to 42/42 completed (AUROC 1.000 either way; Brier 0.0210 to 0.0037); o3 38/42 to 39/42 (AUROC 0.445 to 0.461). Selection caveat: resampling conditions on completions that finish within budget, so the method is structurally biased toward better-looking results even though this run had no cherry-picking (every sample resolved on its single retry). Original pre-completion records: results_checkable_before_completion_20260712.jsonl. Raw transcripts: the two 2026-07-12T16-30* logs in logs_inspect_checkable/. Total cost: $17.12.
