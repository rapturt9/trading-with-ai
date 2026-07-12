# Full raw trace evidence

One file per representative interaction. Each file is RAW and untrimmed: the complete prompt actually sent, the model's full reasoning content where the provider returned it, the full visible response, and the scored outcome, clearly delimited by `====` bars. Nothing here is paraphrased. Open a file to read exactly how one interaction went.

Provenance sources:
- The checkable-rendering redesign, control run, and probes come from the Inspect `.eval` logs in [`../../logs_inspect_v2/`](../../logs_inspect_v2), extracted per sample by `zipfile` plus `json` (the raw-zip path, since `read_eval_log()` fails on the `reasoning_effort="max"` logs). Model reasoning is in the assistant message's `reasoning` content block; the visible answer is the `text` block.
- The max-effort raw-trace run (binary) comes from the per-call cache in [`../../cache/`](../../cache), located by reconstructing the cache key with `run_experiment.py`'s own `cache_key(model, prompt, idx, tag)` function (not reimplemented). Cache entries from 2026-07-07 on store the prompt, the reasoning content, the response, and any refusal text.

The idx-56 trace (a middle-bucket tamper at round 29, seed 57) recurs across several files on purpose: it is the same trace seen by many models under both renderings, so the files together are a controlled cross-model, cross-rendering contrast on ONE input.

| File | Interaction | Scored outcome | Backs claim |
|---|---|---|---|
| [`01_opus46_dual_idx56_CATCH.txt`](01_opus46_dual_idx56_CATCH.txt) | claude-opus-4.6, checkable DUAL rendering, tamper at round 29 | TP_r4r (VERDICT TAMPERED, ROUND 29) | Claim 1 / 1a: detects and localizes on the checkable rendering (42/42) |
| [`02_opus46_binary_idx56_MISS.txt`](02_opus46_binary_idx56_MISS.txt) | claude-opus-4.6, SAME trace, raw BINARY rendering (Phase 1b) | FN (VERDICT GENUINE) | Claim 1: the 19 percent ceiling. Same input, only the rendering changed, and the model misses it |
| [`03_gpt55_binary_idx56_carryslip_MISS.txt`](03_gpt55_binary_idx56_carryslip_MISS.txt) | gpt-5.5, SAME new prompt and JSON schema, OLD binary rendering, same trace | FN (33 wrong sums in its own audit) | Claim 1b (attribution): with only the rendering reverted to binary, the model slips carries and misses |
| [`04_gpt55_binary_idx4_genuine_FALSEFLAG.txt`](04_gpt55_binary_idx4_genuine_FALSEFLAG.txt) | gpt-5.5, binary rendering, a GENUINE trace | FP (VERDICT TAMPERED; 17 wrong sums; the verdict-driving mismatch is a Sigma0 bit error it "confirmed" on recheck) | Claim 3 / 1b: the two-sided failure. Its own binary computation slip manufactures a false flag on a clean trace |
| [`05_gpt55_dual_idx56_CATCH.txt`](05_gpt55_dual_idx56_CATCH.txt) | gpt-5.5, checkable DUAL rendering, same round-29 trace | TP_r4r (VERDICT TAMPERED, ROUND 29) | Claim 1a: the same model catches the same tamper once the trace is decimal-rendered |
| [`06_o3_dual_idx56_barely_engaged_MISS.txt`](06_o3_dual_idx56_barely_engaged_MISS.txt) | o3, checkable DUAL rendering, same trace | FN (reported 0 sums; "Computation not performed within current resource limits") | Claim 2b: o3 does not engage the audit even on the checkable rendering, so it is off-trend, not a capability data point |
| [`07_gpt4o_dual_idx1_no_reasoning_FALSEFLAG.txt`](07_gpt4o_dual_idx1_no_reasoning_FALSEFLAG.txt) | gpt-4o, checkable DUAL rendering, a GENUINE trace, no reasoning channel | FP (VERDICT TAMPERED) | Claim 2a: with no hidden reasoning channel it cannot hold the checks and false-flags a clean trace |
| [`08_fable5_refusal_idx0.txt`](08_fable5_refusal_idx0.txt) | claude-fable-5 (top ECI), a genuine trace | UNPARSEABLE (content-policy refusal, response None) | Claim 2 anomaly: the top-ranked model refuses the task outright (8/8), zero data |
| [`09_opus48_budget_exhaustion_idx0.txt`](09_opus48_budget_exhaustion_idx0.txt) | claude-opus-4.8, a genuine trace, DUAL rendering | UNPARSEABLE (stop_reason max_tokens; 71k reasoning tokens, zero visible answer) | Claim 2 anomaly: it reasons to the 128k output cap and never emits a verdict, even under the bounded schema |

## Reproduce any file

- Inspect-sourced files: `python3` with `zipfile.ZipFile(<eval>).read("samples/<idx>_epoch_1.json")` then read `messages[0].content` (prompt), the assistant message's `reasoning` and `text` content blocks, and `scores.r4r_v2_scorer.metadata` (outcome). The eval-to-model map is in [`../README.md`](../README.md) and by `header.json`'s `eval.model` field.
- Cache-sourced files: import `run_experiment` and `score`, build the dataset with `build_dataset(64)`, render the trace with `render_trace(item["trace"], base="binary", decompose_add=True)`, wrap with `build_prompt(...)`, and load `cache_path(cache_key(model, prompt, idx, tag="maxeffort-binary-64"))`.
