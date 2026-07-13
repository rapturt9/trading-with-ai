# The verification horizon: how long a cryptographic trace can a model verify?

The horizon experiment behind **Figure 3** of the LessWrong post "Making credible deals with AIs" by Ram Potham. It extends the root SHA-256 tamper experiment (repository root) to longer and harder traces and measures how the reliable verification length grows across model release dates.

**Confidence: Medium on the proxy fit, Low on the dated crossings.** The horizon is fit on small samples and an easier proxy axis, so the dates are an optimistic upper bound, not a calendar commitment (see the honesty notes below).

## What this measures

A model's ability to catch a single planted error in a computation trace has a length limit. Past some number of operations, its own compounding arithmetic errors defeat the check.

**N90 = the trace length, in word-level operations, at which a model's tamper-detection reliability stays at 90%.** This is the exact-verification analog of METR's time horizons, and arguably sharper, because compounding errors make the reliable length brutally sensitive to per-operation error. N90, not the 50% crossing (N50), is the deployment-relevant bar: a coin-flip verifier is worse than none, because a check that wrongly passes a fake makes the AI more confident in the fake than if it had never checked. One operation is one printed, checkable line; inputs and constants do not count, and a multi-word multiplication renders as a handful of row lines, never a quadratic blowup.

The target scale is real signature verification: a full NIST P-256 ECDSA verify is roughly 410,000 to 800,000 operations, and a full TEE attestation check runs into the millions.

## Result

The horizon is fit on a **small-curve / SHA proxy axis**, and real P-256 diverges harder. Real 256-bit arithmetic is measurably harder than the same computation over a small curve at matched length, and the two do not overlay (found, not assumed: pooling them produced a nonsensical negative-width bracket for o3). On real P-256, today's models already collapse to about 0% detection by a few hundred operations, far short of the small-curve horizon.

Measured points (small cells, 2 to 8 traces each, so directional):

| Model | ECI | Release (GA) | Small-curve / SHA horizon | On real P-256 |
| --- | --- | --- | --- | --- |
| gpt-4o | 129.3 | 2024-05 | floor, 0% everywhere (not length-driven) | 0% everywhere |
| o3 | 147.1 | 2025-04 | N50/N90 bracketed 321 to 448 ops | already 0% by ~202 to 270 ops |
| gpt-5 | 150.0 | 2025-08 | N50 ~448 ops, N90 ~415 ops (90% CI [24, 422]) | already 0% by ~470 ops |
| claude-opus-4.6 | 155.5 | 2026-02 | 100% through ~896 ops | drops to 0% by ~2,024 ops (first real bound) |

gpt-4o is a floor on both families and is left off the trend line. o3 and opus-4.6 are brackets, not fitted crossings, so read them as directional. opus-4.6's bracket (896, 2024) crosses the small-curve/real-P-256 family boundary, coarser than a same-family bracket.

**On the proxy trend, the N90 horizon roughly doubles every 154 days.** Extrapolated, it reaches full ECDSA-verify length (410k to 800k ops) around **2029-11** and full TEE attestation length (1.2M to 3.2M ops) around **2030-08**.

**Two honesty notes on the dates:**
1. They are extrapolations from three points over small samples, two of them brackets rather than sharp crossings. Treat them as order-of-magnitude, not calendar commitments.
2. They are read off the easier small-curve/SHA proxy. On real P-256 every model collapses much earlier, so the plotted horizon is an **optimistic upper bound**, not the real-P-256 frontier, which today is much shorter.

Plot: `verification_horizon_measured.png` (N50 and N90 vs release date, with the ECDSA and TEE-attestation bands and the trend-line crossing dates marked).

## Design

Every trace-generator family extends, not duplicates, the root `../src/sha256_trace.py`. A tampered trace has exactly one planted bit flip and leaves exactly one locally-inconsistent line; a genuine trace has none. Every family is cross-checked against an independent ground truth (`hashlib.sha256` for SHA, a from-scratch Jacobian-coordinate reference verify for both ECDSA families).

1. **Multi-block SHA-256** (`sha256_multiblock.py`): real Merkle-Damgard chaining, 448 operations per 64-byte block. The dense, cheap length axis.
2. **Small-curve ECDSA** (`ecdsa_trace.py`): a constructed 8/12/16-bit prime-field curve, the full ECDSA verification algorithm traced at word scale. The secondary comparison family.
3. **Real P-256 fragments** (`p256_trace.py`, primary): real NIST P-256 curve constants, contiguous 1/2/4/8-operation spans drawn from a genuine complete verification, every multiplication linearly decomposed into word-scale lines. This is the real primitive a hardware attestation checks.
4. **Report-shaped SHA payloads** (`report_payload.py`): family 1's machinery hashing an attestation-report-style message.
5. **Composite mini-attestation** (`mini_attestation.py`): families 3 and 4 chained (hash a report, verify a real P-256 signature over its digest), the closest this project gets to the real TEE-attestation mechanism. Built and self-tested; not yet run against a model.

**Scoring.** Right-for-right-reason on an exact 3-part location: `(block, round, field)` for SHA, `(section, op_idx, step)` for ECDSA. A `TAMPERED` verdict counts only if the model names that exact location.

**Two limits on every number.** Tampers are non-adversarial single-bit flips (nobody searches for the hardest tamper for a given model), and every call runs with full uncapped chain-of-thought. Both make these reliability figures an upper bound on real-world robustness.

## Reproduce

```
cd verification-frontier

# 1. Self-tests: all 5 generator families across the full seed x rung x bucket x
#    class sweep, plus the example artifacts. Zero API calls, ~1-2 min.
python3 stage0_selftest.py
# Expect: "=== TOTAL: 0 failures across all self-tests ==="

# 2. Token dry run: exact token counts per rung, every family. Zero API calls.
python3 token_dry_run.py

# 3. Analysis of the already-collected logs (zero new API calls): per-condition
#    outcomes, real cost from token usage x live prices, and the N50/N90 logistic
#    fits, fit SEPARATELY per model x family-group (small-curve vs real-P-256),
#    with bootstrap CIs and apparatus-failure exclusion.
python3 analyze_pilot.py

# 4. The horizon plot (N50 + N90 vs release date, TEE/ECDSA bands, trend crossings):
python3 make_ops_horizon_plot_v2.py     # writes verification_horizon_measured.png
```

The paid runs below are already cached. Rerunning makes new paid calls unless every `-T` param and the log-dir match an existing `.eval` exactly, in which case Inspect's native cache replays for $0. Requires `OPENROUTER_API_KEY`.

```
# SHA family (rung = n_blocks, 448 ops/block):
inspect eval inspect_task_frontier.py --model openrouter/openai/gpt-5 \
    -T family=sha -T model_key=openai/gpt-5 -T rung=1 -T n=4 --log-dir logs_pilot

# Small-curve ECDSA family (rung = field bits, 231 ops at bits=8):
inspect eval inspect_task_frontier.py --model openrouter/openai/o3 \
    -T family=ecdsa -T model_key=openai/o3 -T rung=8 -T n=8 --log-dir logs_pilot

# Real P-256 fragment family (rung = n_ops: 1/2/4/8 contiguous point ops):
inspect eval inspect_task_frontier.py --model openrouter/anthropic/claude-opus-4.6 \
    -T family=p256 -T model_key=anthropic/claude-opus-4.6 -T rung=8 -T n=4 --log-dir logs_live
```

The full set of `-T rung` / `-T n` combinations run across all four models produced the `logs_pilot/*.eval` and `logs_live/*.eval` logs in this folder; `analyze_pilot.py` reads them directly, so step 3 above reproduces every number with zero new spend.

**Parent extension note.** Every module here imports from `../src/sha256_trace.py`, extended with backward-compatible keyword arguments. Re-running the parent's own self-test after the extension reproduces byte-identical output to what is committed there; the extension is additive.

## Evidence

- `verification_horizon_measured.png`: the horizon plot (Figure 3), N50 and N90 points and brackets vs release date, with the ECDSA and TEE bands and crossing dates.
- `artifacts/selftest_summary.txt`: the full self-test log, every family x rung x bucket x class, 0 failures.
- `artifacts/example_*.txt`: a complete rendered trace pair per family (genuine and tampered), the tampered one flagged at exactly one line and hand-checkable (e.g. the small-curve ECDSA pair: `(138 - 183) mod 223 = 178`, printed value `162`).
- `logs_pilot/*.eval`, `logs_live/*.eval`: the Inspect logs, readable via `inspect view` or `read_eval_log`. `analyze_pilot.py` computes every reported number from these.
- `artifacts/traces/`: extracted per-outcome trace files (`extract_traces.py`).
