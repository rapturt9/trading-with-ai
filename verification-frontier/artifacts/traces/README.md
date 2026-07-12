# Trace index

Ten complete, unmodified model interactions from `../../logs_pilot/*.eval`, extracted by
[`../../extract_traces.py`](../../extract_traces.py) (zero new API calls; reads the already-collected
pilot logs). Each file has the exact prompt as sent, the model's full reasoning content where the
provider returns it as readable text, the full visible output, and the scored outcome, all read
verbatim from `Score.metadata` and `ModelOutput` -- nothing paraphrased, nothing hand-typed except
this index.

**Reasoning-content caveat, found while building this index.** OpenAI models (gpt-5, o3) return
their reasoning as an **encrypted, non-human-readable blob** through this OpenRouter code path (a
Fernet-token-shaped ciphertext, no whitespace, tens of KB) -- billed and real (`usage.reasoning_tokens`
is nonzero) but not inspectable by a third party. Anthropic's opus-4.6 returns real plain-text
reasoning through the identical extraction code path, so this is a provider behavior difference, not
an extraction bug. gpt-4o returns no reasoning channel at all (`reasoning_tokens=0`). Each file states
which case applies. Practical effect: only the two `opus46_*.txt` files below have inspectable
reasoning; every other file's "reasoning" section is either encrypted-blob-noted or absent-noted, and
the audit trail for those models rests on their visible output text plus the scorer's structural
checks.

| File | Model | Family / op count | Kind | Scored outcome | What it evidences |
|---|---|---|---|---|---|
| [`gpt5_TP_r4r_ecdsa231.txt`](gpt5_TP_r4r_ecdsa231.txt) | gpt-5 | toy-ECDSA, n_ops=289 (bits=8 rung) | tampered | TP_r4r | gpt-5 correctly names the exact tampered line at the ECDSA-231 rung, the high end of its decay curve |
| [`gpt5_FN_sha448.txt`](gpt5_FN_sha448.txt) | gpt-5 | SHA, n_ops=448 (1 block) | tampered | FN | gpt-5 missing a tamper at N=448, the pooled 50% decay point (this pilot's n=2 half of the pooled n=44) |
| [`gpt5_FN_sha896.txt`](gpt5_FN_sha896.txt) | gpt-5 | SHA, n_ops=896 (2 blocks) | tampered | FN | gpt-5 missing a tamper at N=896, the 0% point that anchors the N50~=448 logistic fit from above |
| [`gpt5_TN_sha448.txt`](gpt5_TN_sha448.txt) | gpt-5 | SHA, n_ops=448 (1 block) | genuine | TN | gpt-5 correctly calling a genuine SHA-448 trace clean |
| [`opus46_TP_r4r_sha448.txt`](opus46_TP_r4r_sha448.txt) | claude-opus-4.6 | SHA, n_ops=448 (1 block) | tampered | TP_r4r | opus-4.6 correct at N=448, part of its 100%-through-896 saturation |
| [`opus46_TP_r4r_sha896.txt`](opus46_TP_r4r_sha896.txt) | claude-opus-4.6 | SHA, n_ops=896 (2 blocks) | tampered | TP_r4r | opus-4.6's ONE measured N=896 tampered sample -- still correct, the basis for "opus remains unbounded above 896" |
| [`opus46_TN_sha448.txt`](opus46_TN_sha448.txt) | claude-opus-4.6 | SHA, n_ops=448 (1 block) | genuine | TN | opus-4.6 correctly calling a genuine SHA-448 trace clean; also the file with fully readable plain-text reasoning, useful as a reference for what "full reasoning" looks like when the provider actually returns it |
| [`o3_TP_r4r_ecdsa231.txt`](o3_TP_r4r_ecdsa231.txt) | o3 | toy-ECDSA, n_ops=231 (bits=8 rung, exact match) | tampered | TP_r4r | o3 correct at the ECDSA-231 rung, the upper bracket edge for o3's N50 in (231, 448) |
| [`gpt4o_FP_genuine_ecdsa231.txt`](gpt4o_FP_genuine_ecdsa231.txt) | gpt-4o | toy-ECDSA, n_ops=231 (bits=8 rung, exact match) | genuine | FP | the miscalibration finding: gpt-4o calls a GENUINE trace tampered, asserting a specific wrong location with p=1.00 and no real supporting derivation in its visible text |
| [`gpt4o_TP_wrongloc_ecdsa231.txt`](gpt4o_TP_wrongloc_ecdsa231.txt) | gpt-4o | toy-ECDSA, n_ops=231 (bits=8 rung, exact match) | tampered | TP_wrong_loc | the miscalibration finding, tampered side: gpt-4o correctly says TAMPERED but names the wrong line, again confidently |

**Provenance for every file.** Each file's own header states: source `.eval` filename, sample index,
`model_key`/`api_model`/ECI, family/rung/exact n_ops, kind, tamper bucket/seed/op_type, ground-truth
location (`gt_loc`), `reasoning_effort`/`max_tokens`, rendering/prompt variant, `git_commit`, provider
`stop_reason`, and per-call token usage -- all read directly from `Score.metadata` and `ModelOutput`,
none of it re-derived or hand-typed.

**Selection note.** Several rungs have more than one sample matching a requested case (e.g. gpt-5 has
2 TP_r4r ECDSA-231 samples); one representative was picked per case. The full set for any condition is
in the corresponding `logs_pilot/*.eval` file, viewable with `inspect view` or `read_eval_log`.

**Regeneration note (added after a file-loss incident, 2026-07-12).** These 10 files plus this index
were deleted once from disk shortly after being written and briefly git-committed -- most likely a
race with this vault's autosync cron (`-X ours` merge) or a concurrent teammate's file operation in
this same shared session, not this script's own doing (`extract_traces.py` never deletes anything, only
writes). Regenerated by rerunning `python3 extract_traces.py` (zero new API calls, deterministic from
`logs_pilot/*.eval`). If these files go missing again, rerun that command rather than treating it as
data loss -- nothing here depends on non-reproducible state.
