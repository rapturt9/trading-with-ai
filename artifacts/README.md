# Phase 3 audit artifacts

One proving artifact per pipeline step, so a human auditor can verify every
headline claim without rerunning anything. Regenerate all of these with the
commands in the repo `README.md` Reproduce block (Phase 3 section).

## Stage 0 (zero API) — built and verified before any spend

| Artifact | Proves | Produced by |
|---|---|---|
| `stage0_selftests.txt` | generator matches hashlib; `score.py` + `score_v2.py` self-tests pass (8 audited bug classes + metric hand-checks); dry-run token counts match the proposal; the local-consistency invariant holds over all 84 traces. | `python3 stage0_render.py` and the self-test scripts (transcript). |
| `example_genuine_dual.txt` | the dual (binary+decimal) rendering of a GENUINE trace (idx 0, seed 1); `local_consistency_report` returns `[]` (no inconsistent lines). | `python3 stage0_render.py` |
| `example_tampered_dual.txt` | the dual rendering of a TAMPERED trace (idx 42, round 16), with the single inconsistent line (`new a`) marked `>>> TAMPERED LINE >>>`; every other line, including all downstream rounds, checks out. | `python3 stage0_render.py` |
| `example_tampered_round_excerpt.txt` | the 20-line tampered round in isolation: printed `new a = 2159474747` but `temp1 + temp2 mod 2^32 = 2159474811` (differ by 64 = one flipped bit). | `python3 stage0_render.py` |

## Full run (completed)

| Artifact | Proves | Produced by |
|---|---|---|
| `phase3_metrics_table.txt` | the full metric suite per model (detection, specificity, AUROC+CI, TPR@5%FP, Brier, arithmetic-error, per-position, UNPARSEABLE) + pilot gates + total cost, all from the `.eval` logs. | `python3 analyze_v2.py --gates` |
| `sample_eval_excerpt.txt` | one opus-4.6 sample: full provenance block + visible JSON audit output + confirmation reasoning content is captured in the log. | read from `logs_inspect_v2/*.eval` |
| `replay_zero_calls.txt` | the zero-new-call replay: re-running gpt-4o full via Inspect cache uses `openrouter 0/30` connections (0 API calls), 10s vs 80s, and re-derives byte-identical outcomes. | re-run `inspect eval ... gpt-4o` |
| `detection_r4r_vs_eci_v2.png`, `specificity_vs_eci_v2.png`, `phase1b_vs_phase3_r4r.png` | detection/specificity scale with ECI; Phase 1b->Phase 3 before/after (opus 8->42, gpt-5.5 5->37, gpt-5 0->22 of 42). | `python3 make_plots_v2.py` |

Full per-line provenance is in `../results_v2.jsonl`.
