# Verification frontier: internal research report

**LIVING REPORT.** This covers Stage 0/0b/0c (build, zero cost) and the pilot ($45 cap approved,
$20.37 actually spent, 38 real calls made -- see the call-count discrepancy note in the Cost ledger).
The live grid ($250-500, hard cap $600) is pre-authorized but not yet run. This report will be
refreshed, not replaced, when the live grid lands -- new sections appended, nothing here silently
edited out.

This is the observable internal record for the experiment. It refers by name to two private working notes, `proposal.md` (the pre-registered design) and `plan.md` (the append-only run log), which are not included in this public package; where the text points to them, the fuller detail lives there, while every number below is reproducible from the code, logs, and results committed in this folder.

**One-line claim:** on the best checkable rendering tested so far, gpt-5's tamper-detection
reliability crosses 50% at almost exactly N=448 word-level operations and crosses 90% (the
deployment-relevant threshold -- see "N50 vs. N90" below) at N90~=383 ops, a much smaller gap between
the two than a simple compounding-error model would predict; o3 crosses somewhere between 231 and 448
ops for N50, with N90 loosely below that; opus-4.6 has not yet been made to fail at up to 896 ops for
either threshold; and gpt-4o fails not by disengaging but by confidently asserting the wrong tamper
location on 8/8 ECDSA samples -- four distinct pictures of the same underlying question, not one clean
curve, from a pilot that intentionally spent under half its $45 cap to buy real per-call cost data
before committing to the full live grid.

**Epistemic status:** Medium on the gpt-5 N50/N90 point estimates (real fit, real crossings, but n=44
pooled and only 2 pilot-native tampered samples at the anchoring N=896 rung). Low-Medium on the
o3/opus-4.6 N50 brackets, and lower still on their N90 implications, which this report derives from the
same thin data with extra statistical-power caveats (see C2/C3 below). Medium-High on the gpt-4o
failure-mode finding (n=8, unanimous, directly inspected, not a parsing artifact). Every number below
was recounted from `logs_pilot/*.eval` via `analyze_pilot.py` or a direct `read_eval_log` script written
for this report, not copied from `plan.md`'s prose -- see the Cost ledger section for one place where
that recount caught a real error in the prose. **An independent adversarial audit (see Methodology)
found the ECDSA renderer leaks the binary verdict via a structural comparison line -- every ECDSA
VERDICT-level number here is confounded and location-metric-only valid, but the r4r location metric
every ECDSA claim actually rests on is audit-confirmed not inflated by it (~0.4% blind-guess rate over
231 lines).** SHA claims are unaffected. See the top Limitations bullet for the full statement.

---

## Methodology

### Task definition

**N50(model, task_family) = the smallest trace length N (in tracked word-level operations) at which
the model's tamper-detection reliability, measured on the pre-registered checkable rendering, falls to
50%.** Reliability is estimated at each tested N from genuine + tampered traces, then a logistic curve
is fit in log(N) to estimate N50, rather than reading off a single threshold-crossing sample. Full
definition and rationale: `proposal.md`'s "Definition" and "Sampling design" sections.

**N90(model, task_family), added to this report per Ram's request, is the same definition at the 90%
reliability threshold instead of 50%.** N50 is kept throughout for comparability with METR's own
time-horizon convention (its headline number is also a 50%-reliability crossing). But 50% is a coin
flip: a deal-verifier, attestation checker, or signature auditor that is right half the time is not
trustworthy at any deployment-relevant sense of the word.

**Ram's own rationale for why N90, not N50, is the deployment-relevant horizon, stated plainly here
rather than left implicit:** a mid-reliability verifier is worse than no verifier at all, in one
specific direction. A check that wrongly PASSES a fake makes the AI relying on it MORE confident in the
fake than if it had never checked -- the check's silence gets read as an endorsement. At 50%
reliability, verification actively LAUNDERS fabrications half the time: a fabricated deal, signature, or
attestation that would have been treated with appropriate suspicion on its own instead gets waved
through with the verifier's implicit stamp of approval, roughly as often as it gets caught. At 90%+
reliability that laundering channel narrows sharply (only 1 fabrication in 10 slips through instead of
1 in 2). **This is why N90, not N50, is the threshold this project treats as deployment-relevant for
deals** -- the trace length at which a model is wrong on no more than 1 in 10 tamper checks, not merely
better than a coin flip.

Every claim below now reports both thresholds, computed from the exact same fitted `(a, b)` parameters
`analyze_pilot.py` already produces for N50 (solving `logistic(logN) = p` for `N50` at `p=0.5` and for
`N90` at `p=0.9`, not two separate fits), so N90 is free once a model's fit exists -- see "N50 vs. N90"
under Claims below for the numbers and their honesty caveats.

Two task families ran real API calls in this pilot:

- **SHA multi-block** (`sha256_multiblock.py`): real Merkle-Damgard chaining, 448 tracked operations
  per 64-byte block (each round contributes 7 modular additions per the the root SHA-256 experiment "448
  ops/block" convention). Rungs tested: n_blocks=1 (448 ops), n_blocks=2 (896 ops).
- **Toy-field ECDSA** (`ecdsa_trace.py`): a constructed 8-bit-prime curve (`Curve(p=223, b=5, n=229,
  h=1)`), the full ECDSA verification algorithm (header, two double-and-add ladders, final point
  addition, final comparison) traced at word-scale precision. Rung tested: bits=8, nominally 231
  operations, though individual traces in this pilot ranged 231-331 lines depending on tamper
  class/seed (the toy curve's op count is not perfectly fixed per instance -- see `proposal.md`
  Family 2 for why).

A **third family, real P-256 verification fragments (`p256_trace.py`), is built and self-tested
(0 failures) but was NOT run in this pilot** -- it is scoped as the PRIMARY family for the live grid,
per Ram's "similar to what is done for TEE" escalation (`plan.md`, "Pilot RUN" entry). No claim below
covers it; it is out of scope for this report until the live grid runs.

### Scoring rule, verbatim (`score_frontier.py`, `score_frontier()`)

```
TN            genuine, called GENUINE
FP            genuine, called TAMPERED
FN            tampered, called GENUINE
TP_r4r        tampered, called TAMPERED, location EXACTLY matches
TP_wrong_loc  tampered, called TAMPERED, location does not match
UNPARSEABLE   no verdict recovered from either channel
```

"Location" is a 3-part tuple read directly off each generator's own `local_consistency_report(trace)[0]`
(never hand-derived): `(block, round, field)` for SHA (e.g. `(0, 41, "new_a")`), `(section, op_idx,
step)` for ECDSA (e.g. `("ladder2", 2, "y3")`). **A TAMPERED verdict counts as correct (TP_r4r) only
if the model names this exact 3-part location** -- calling TAMPERED with the wrong block/round/field
(SHA) or wrong section/op_idx/step (ECDSA) scores `TP_wrong_loc`, not a hit. "Tamper-detection
reliability" in every claim below means the **TP_r4r rate among tampered samples only** (matches how
`../README.md` cites "100%/88%/52%" for opus-4.6/gpt-5.5/gpt-5 -- each is that model's
TP_r4r/42 on the SHA-448 dual condition, independently confirmed against `results_v2.jsonl` by
`analyze_pilot.py`'s `load_parent_sha448()`).

### Op-counting convention (locked, `proposal.md`, verbatim)

> 1 op = 1 printed derived value = one checkable line, in a canonical rendering where every line is one
> word-scale operation. Only *derivable* lines count (inputs and constants are excluded); they are
> simultaneously the workload, the checkable surface, and the tamper-target set.

A big operation never counts as one op: multiplications decompose **linearly, not pointwise** (grade-
school long multiplication: ~n lines for an n-word operand, not n²) -- measured 4.0x line-count
reduction on a real 256-bit x 256-bit multiply (16 lines linear vs. 64 pointwise), landing in the
predicted 3-4x range. Every line is tagged by op type (addition/multiplication/reduction/
bitwise/inverse-check); the reliability model is the product over the trace's actual type mix of
per-type rates, not a single-p power law.

### Models, ECI, release dates

**All release dates below are now confirmed against public sources (previously two were TBD in
`proposal.md`; both filled in here).** Convention: **general-availability (GA) date**, i.e. when the
model became usable via API/product, not an announcement or preview date -- stated explicitly because
it matters for o3 (see note below) and is the only convention that makes the dates comparable to each
other as a real usage-trend axis.

| Model | ECI | Release date (GA) | Source | Ran in this pilot? |
|---|---|---|---|---|
| gpt-4o | 129.3 | 2024-05-13 | openai.com/index/hello-gpt-4o | yes (ECDSA-231, n=8) |
| o3 | 147.1 | 2025-04-16 | openai.com/index/introducing-o3-and-o4-mini | yes (ECDSA-231, n=8) |
| gpt-5 | 150.0 | 2025-08-07 | openai.com/gpt-5 | yes (SHA-448/896, ECDSA-231; n=12 total) |
| claude-opus-4.6 | 155.5 | 2026-02-05 | anthropic.com/news/claude-opus-4-6 | yes (SHA-448/896, ECDSA-231; n=10 total) |
| gpt-5.5 | 158.5 | 2026-04-24 (API GA) | openai.com/index/introducing-gpt-5-5 | **no** -- only parent data (root SHA-256 experiment) (N=448, 88%) exists for this model |
| claude-fable-5 | -- | 2026-06-09 | anthropic.com/news/claude-fable-5-mythos-5 | **excluded from this study** (refused 8/8 pilot traces outright in the parent run (root SHA-256 experiment), per `proposal.md`'s Models section; listed here for reference only, no ECI/reliability data exists for it in this project) |

**o3 date note:** OpenAI announced o3 in December 2024 but that was a preview/announcement, not a
release -- no public API access existed until the April 2025 GA alongside o4-mini. 2025-04-16 (the GA
date) is used here, not the December 2024 announcement, for consistency with the GA convention above.

**gpt-5.5 date note:** two dates exist -- 2026-04-23 (ChatGPT product release) and 2026-04-24 (API GA).
This project calls every model via OpenRouter/API (see `README.md`'s Reproduce block), so **the API GA
date (2026-04-24) is the one used here**, not the one-day-earlier ChatGPT date, for consistency with how
every other model's date in this table was determined (when it became API-callable, not when a chat
product shipped).

ECI source: `epoch.ai/data/eci_scores.csv`, 2026-07-08 snapshot (same as parent). With both dates now
confirmed, the release-date axis of the eventual headline N50/N90-vs-release-date plot (secondary to
the always-available ECI axis) is unblocked for the live grid.

### Per-rung line and token counts (Stage 0/0c, zero API calls, from `token_dry_run.py`)

| Family | Rung | Op lines | Tokens |
|---|---|---|---|
| SHA dual, n_blocks=1 | 448 ops | 448 | ~57,207 |
| SHA dual, n_blocks=2 | 896 ops | 896 | (not separately re-measured here; scales ~linearly, see `proposal.md`) |
| Toy-ECDSA, bits=8 | 231-263 ops (self-test range) | 231-263 | ~4,050 |
| Toy-ECDSA, bits=12 | 366-440 ops | 366-440 | ~7,538 |
| Toy-ECDSA, bits=16 | 462-556 ops | 462-556 | ~10,276 |
| P-256 fragment, n_ops=1/2/4/8 (built, not run) | 202/472/944/1,956 | same | 10,142/23,377/46,513/96,052 |
| Composite (report+P-256), p256_n_ops=1..8 (built, not run) | -- | -- | 73,551/83,505/106,636/156,265 |

Full table and every family's rendering/tamper-mechanism detail: `proposal.md`.

### Locked predictions (cross-reference: `plan.md`, "2026-07-12, Predictions LOCKED" entry)

Back-of-envelope, single-data-point-per-model anchors, locked BEFORE the pilot ran:

| Model | Predicted N50 | Confidence |
|---|---|---|
| gpt-4o | not measurable (predicted "won't clear 50% at any tested rung", engagement-floor framing) | High on direction, N/A on a number |
| o3 | same as gpt-4o | High on direction, N/A on a number |
| gpt-5 | 470-550 ops | Medium |
| claude-opus-4.6 | 10,000-30,000 ops | Low |
| gpt-5.5 | 2,000-3,000 ops | Medium |

Plus: an overlay/divergence framing for SHA-vs-ECDSA at matched op count (Ram's prior: near-overlay,
ECDSA slightly below via multiplication-row lines), and a doubling-time extrapolation (~2-4 months per
doubling, ECDSA-band crossing ~16-32 months from gpt-5.5's release, Low confidence). See "Prediction
comparison" under Claims below for how these held up.

### Independent adversarial audit (credited, 2026-07-12)

An independent adversarial cheating audit ran against this pilot's data, separate from this report's
own authorship. Its two headline findings, as reported to this report's author (the two specific rates
below -- ~98.7% and ~0.4% -- are the audit's own reported figures, not independently re-derived here):

**CRITICAL-but-contained.** The ECDSA renderer prints the final `v == r ?` comparison as a structural
line (labeled "not a tamper-target line" in every extracted trace, e.g. `L0254: Final comparison ...
v == r ? True`) -- this leaks the binary GENUINE/TAMPERED verdict directly, in an estimated ~98.7% of
cases (the ~1.3% miss rate matches the toy-field coincidence `proposal.md` already documents under "one
rare exception," where a corrupted trace can coincidentally still show `v == r ? True`). **Every ECDSA
VERDICT-level outcome in this pilot (whether TN/FP counts -- did the model correctly say GENUINE vs.
TAMPERED -- are confounded) should be read as "location-metric-only valid," not as evidence the model
derived the verdict itself from the trace's arithmetic.** The audit separately confirmed the **primary
r4r location metric is NOT inflated by this leak**: independently re-scoring all 38 pilot completions
against the same 3-part location rule matched every recorded outcome exactly (the 4 gpt-4o
wrong-location cases were correctly scored as misses, not accidental hits), and the blind-guess rate for
naming the exact correct location by chance is ~0.4% over 231 tamperable lines at this rung -- far too
low to explain any TP_r4r result as luck. The renderer is being fixed to drop the leaked comparison
line; post-fix runs will carry a version marker so pre-fix and post-fix ECDSA data are never silently
pooled together.

**A confirming case found directly in this report's own already-extracted traces (checked here, not
audit-reported):** the tampered sample behind C1's ECDSA-231 TP_r4r point (`gpt5_TP_r4r_ecdsa231.txt`)
has the leaked line read `v == r ? True` -- **misleadingly indicating "genuine"** despite the trace
being genuinely tampered (the same rare toy-field coincidence the audit's ~1.3% figure refers to) --
yet gpt-5 still correctly called TAMPERED and named the exact corrupted line. Since the leak pointed the
WRONG way on this specific sample, that correct call cannot have come from reading the leaked line; it
is real evidence of detection. By contrast, o3's ECDSA-231 TP_r4r sample (`o3_TP_r4r_ecdsa231.txt`,
behind C2) has the leak reading `v == r ? False` (correctly indicating tampered) -- consistent with the
leak, so that sample's VERDICT could in principle have been leak-derived even though its LOCATION (the
r4r-qualifying part) could not have been. gpt-4o's two ECDSA samples (behind C4) are checked in C4
below.

**CLEAN findings, credited as positive audit evidence.** No ground-truth markers were found in any of
the 38 real prompts (the vault's own example-file debug headers, e.g. the `local_consistency_report`
annotations used in `proposal.md`'s illustrative excerpts, never reach the model-facing prompt text). No
format distinguishability was found between genuine and tampered SHA traces (identical line counts,
matching digit-length distributions) -- ruling out a model detecting "tampered" from surface statistics
rather than content. Scoring integrity was independently confirmed (recomputing outcomes from raw
completions against ground truth matched `score_frontier.py`'s recorded outcomes exactly). Per-condition
genuine/tampered sample balance was exact throughout (matches the Runs table's `n` column below).

---

## Design decisions

| Decision | What changed | Why | Provenance |
|---|---|---|---|
| ECDSA family redesigned: toy the field, not the scalar | v1 kept real 256-bit secp256k1, shortened only the scalar, point-granularity lines. Replaced with an 8/12/16-bit toy-field curve, full verify algorithm, word-scale lines. | Point-granularity lines hide the actual per-op arithmetic a model has to check; word-scale toy-field lines match the op-counting convention used everywhere else. | `plan.md`, "2026-07-12, ECDSA family redesigned" |
| Decomposition rule: linear, not pointwise | `decompose_multiply` (n² pointwise limb-products) replaced by `decompose_multiply_linear` (grade-school long multiplication, ~n lines). Measured 4.0x reduction on a real 256-bit multiply. | Pointwise decomposition would inflate large multiplications into an unrealistic worst case, breaking the toy-to-real-scale bridge. | `plan.md`, "2026-07-12, Stage 0b" |
| Real P-256 fragments promoted to PRIMARY family | Toy-field ECDSA (8/12/16-bit) demoted to secondary/cheap-dense-sampling; real NIST P-256 curve fragments (contiguous 1/2/4/8-op spans from a genuine signature verify) become the headline ECDSA family for the live grid. | Ram: "I want this to be similar to what is done for TEE" -- real TEE attestation checks a real P-256 signature, not a toy curve. | `plan.md`, "2026-07-12 evening, Pilot RUN" (Family 3 escalation) |
| TEE-attestation-realism items scoped (not built into the pilot) | Report-shaped SHA payloads, P-256/secp256k1 mechanism tagging, composite mini-attestation rung -- all designed, built and self-tested by `frontier-builder` in parallel, but explicitly not run in this pilot. | Building + self-testing new generator code mid-pilot under paid-run time pressure risks an unverified-generator mistake; deferred to the live grid where it can get the same self-test rigor as everything else. | `proposal.md`, "TEE-attestation realism" section; `plan.md` Pilot RUN entry |
| Pre-authorization chain | Stage 0 (build, $0, frontier-builder) -> role-boundary flag (spending real money needs an explicit gate, not just a team-lead ask) -> Fable's gate review confirmed -> $45 pilot cap, probe-first (small n, size the rest from real costs) -> pilot ran, $20.37 spent -> live grid ($250-500, hard cap $600) pre-authorized effective on this pilot report + Stage 0c self-tests, both now true. | Keeps real spend behind an explicit, auditable review gate at every step, per this vault's autonomy-with-corrigibility policy. | `plan.md`, "Predictions LOCKED" (role-boundary flag) and "Pilot RUN" (gate cleared) entries |
| `reasoning_effort="max"` routed through `extra_body` instead of the typed field | The installed `inspect_ai` (0.3.189) rejects `"max"` as an invalid `Literal` for `GenerateConfig.reasoning_effort` (opus-4.6/4.8/fable-5 use `"max"`). Fixed by setting `config.extra_body = {"reasoning": {"effort": effort}}` for any model whose effort string isn't in the valid Literal set. | Found BEFORE any spend: 4 old opus/fable-5 `.eval` logs in `../logs_inspect_v2/` are now unreadable with the current `inspect_ai` for exactly this reason -- writing new pilot logs with the same pattern would have made this pilot's own opus-4.6 data unreadable too. | `plan.md`, "2026-07-12 evening, Pilot harness built" |

---

## Claims

**Two honesty caveats, stated once here and true of every claim below (per `analyze_pilot.py`'s module
docstring):**

1. **Non-adversarial, single-bit tampers.** Every tampered trace has exactly one seeded bit flip;
   nobody searches for the hardest tamper for a given model. These reliability numbers are an upper
   bound on what a verifier achieves against a real adversarial tamperer, not a worst-case measurement.
2. **Full, uncapped chain-of-thought.** Every model call runs with no scaffold and no budget-forcing
   beyond the provider's own `max_completion_tokens`. These numbers describe best-case verification
   conditions, not a CoT-restricted or latency-constrained setting.

**A third limitation, found while building Deliverable 1 (the trace extraction), not previously
documented:** OpenAI models (gpt-5, o3) return their reasoning through OpenRouter as an **encrypted,
non-human-readable blob** (Fernet-token-shaped ciphertext, no whitespace, tens of KB) -- real and
billed (`usage.reasoning_tokens` nonzero) but not inspectable by a third party. Anthropic's opus-4.6
returns real plain-text reasoning through the identical code path. This means the audit trail for
gpt-5/o3's specific failures (below) rests on their visible output text and the scorer's structural
checks, not on inspecting their internal reasoning -- only the two opus-4.6 trace files have readable
reasoning. See `artifacts/traces/README.md` for the full breakdown.

### N50 vs. N90: the theoretical relationship, and what the one real fit shows instead

`proposal.md`'s Goal section states a simplifying theoretical model: if per-operation errors were
independent coin flips at rate p, reliability at length N would be `(1-p)^N`. Under that model, solving
for the two thresholds gives `N50 = ln(0.5)/ln(1-p)` and `N90 = ln(0.9)/ln(1-p)`, so **the ratio
N90/N50 = ln(0.9)/ln(0.5) ~= 0.152 is independent of p** -- recomputed directly here, not copied. That
means, under this toy model, N90 arrives at roughly 15% of N50's op count: a MUCH shorter trace than the
one where reliability first crosses 50%. Combined with a fixed exponential doubling trend in N50 over
time (the pilot's own rough 2-4 month doubling-time estimate, or METR's slower ~7-month figure), the
toy model implies N90 crosses any fixed threshold `T * log2(1/0.152) ~= T * 2.72` months LATER than N50
crosses the same threshold -- roughly 5-11 months under this pilot's 2-4 month estimate, or ~19 months
(~1.6 years) under METR's 7-month figure. This is the basis for "N90-reliable verification arrives years
after N50-reliable, on a fixed doubling trend."

**This toy-model estimate is contradicted by the one real fit this pilot has.** gpt-5's actual 3-point
logistic-in-log(N) fit (`a=86.103, b=-14.1042`, from C1 below) gives N50~=448 and **N90~=383**
(recomputed here: solving `(ln(9)-a)/b` for N90 the same way N50 solves `-a/b`) -- a ratio of
**N90/N50 ~= 0.86**, nowhere near the toy model's 0.152. The measured curve is far STEEPER in log(N)
space than the independent-per-line model assumes: reliability falls from ~90% to ~50% over a narrow
band (383 to 448 ops, a ~17% length increase) rather than gradually across a wide one. If this steepness
holds for other models once they get real fits (not yet true for o3/opus-4.6, both still brackets --
see C2/C3), the practical implication reverses: **N90-reliable verification would arrive close behind
N50-reliable, not years later** -- a materially different, and more urgent, picture than the toy model
suggests.

**Caveat, stated as instructed:** this is one fit, from one model, at n=44/2 pooled/pilot-native
samples per point -- not enough to generalize "the real curve is always this steep." The toy `(1-p)^N`
figure above is kept as the documented theoretical anchor `proposal.md` already commits to, but **any
measured fit (gpt-5's here, and any future model's) supersedes it** wherever both exist; this report
treats the toy-model "years later" framing as falsified for gpt-5 specifically, not confirmed or refuted
for any other model.

### C1. gpt-5's detection reliability decays cleanly across the tested range; N50 ~= 448 ops, N90 ~= 383 ops

100% (2/2 tampered) at N=231 -> 50% (pooled 22/44: 42 from the parent run (root SHA-256 experiment) + 2 from
this pilot, both misses) at N=448 -> 0% (2/2, both misses) at N=896. A joint 3-point logistic fit in
log(N) gives N50 ~= 448 ops (`a=86.103, b=-14.1042`, independently recomputed here: `exp(-86.103 /
-14.1042) = 448.5`), landing almost exactly on the directly-measured 50% point -- a real, non-degenerate
fit, not an artifact. The same fit gives **N90 ~= 383 ops** (`exp((ln(9)-86.103)/-14.1042) = 383.4`,
recomputed here from the identical `(a,b)`, no separate fit needed) -- meaning gpt-5's deployment-relevant
90%-reliability threshold sits only ~17% shorter than its 50%-reliability threshold, not several times
shorter as the toy independent-per-line model would predict (see "N50 vs. N90" above).

**Evidence: STRONG on N50, STRONG-with-the-same-support on N90** (same 3-point fit, same n, no
additional data needed -- N90 is a different point on an already-real curve, not a new extrapolation).
A genuine 3-point fit (not a 2-point bracket where the MLE is unconstrained), crossing lands inside the
tested range, and matches a directly observed rate at the same N.

**ECDSA-leak note (see "Independent adversarial audit" above):** the N=231 anchor point is a
location-metric (TP_r4r) result, which the audit confirmed is not inflated by the ECDSA renderer's
leaked `v == r ?` line; the SHA points (N=448, N=896) are unaffected by this bug family entirely (the
leak is ECDSA-only). The specific gpt-5 sample cited below had the leak read misleadingly (`True` on a
genuinely tampered trace), so its correct call is not explained by the leak either way.

Trace files: [`gpt5_TP_r4r_ecdsa231.txt`](artifacts/traces/gpt5_TP_r4r_ecdsa231.txt),
[`gpt5_TN_sha448.txt`](artifacts/traces/gpt5_TN_sha448.txt),
[`gpt5_FN_sha448.txt`](artifacts/traces/gpt5_FN_sha448.txt),
[`gpt5_FN_sha896.txt`](artifacts/traces/gpt5_FN_sha896.txt). Eval logs:
`logs_pilot/2026-07-12T17-24-09+00-00_..._mtNjJTEWYYiNzzD9xgn7aS.eval`,
`logs_pilot/2026-07-12T17-32-07+00-00_..._Cg4xhDmme3cF6xy7YaN7yW.eval`,
`logs_pilot/2026-07-12T19-08-09+00-00_..._eAeh2AnN4SFXjEKWiEUUTT.eval`, plus
`../results_v2.jsonl` for the pooled N=448 point.

### C2. o3 brackets between (231, 448) ops for N50; N90 loosely below 231, confidently below 448

100% (4/4 tampered) at N=231 -> 0% (0/42, from the parent run (root SHA-256 experiment), not this pilot) at
N=448. With only 2 rungs at opposite extremes, the logistic MLE is numerically unconstrained; its
literal crossing value (13 ops) falls outside the tested range and `analyze_pilot.py` explicitly
detects and discards it rather than reporting a false point estimate. o3's real N50 lies somewhere in
(231, 448) ops, not localized further by this data.

**N90 implication, with real statistical-power caveats (no fit exists, so this is reasoning from the
raw rates, not a computed crossing).** N=448's 0/42 essentially rules out >=90% reliability there
(recomputed: if the true rate were 90%, 42/42 would fail simultaneously with probability
`1 - 0.9^42 ~= 98.6%`, so seeing 0/42 successes is overwhelming evidence the true rate is far below
90%) -- **N90 < 448 is well-established.** But "100% (4/4) at N=231" does NOT tightly localize N90 to
231 or below: recomputed here, if o3's TRUE reliability at N=231 were exactly 90% (not 100%), the
chance of observing 4/4 successes anyway is `0.9^4 = 65.6%` -- a coin-flip-plus is fully consistent with
4/4. **So N=231's "100%" only loosely suggests N90 is at or below 231; it does not rule out N90 sitting
right at ~231 ops, and n=4 is too small to distinguish "truly ~100%" from "truly ~90%, got lucky."**
Honest statement: o3's N90 lies somewhere in a range whose upper bound is confidently below 448 ops and
whose lower bound is only loosely anchored near 231 ops.

**Evidence: STRONG** on the two endpoint rates (real, direct measurements, n=4 and n=42 respectively).
**MEDIUM** on "brackets N50 in this specific interval" as a localization claim -- no interior point was
measured, so the true crossing could sit anywhere in a roughly 2x range. **WEAK** on the N90 lower
bound specifically, for the statistical-power reason above.

**ECDSA-leak note:** the N=231 point is a location-metric (TP_r4r) result, audit-confirmed not inflated
by the leaked `v == r ?` line (~0.4% blind-guess rate over 231 lines). The specific o3 sample cited
below had the leak read correctly (`False`, correctly indicating tampered), so unlike C1's gpt-5
sample, this one's VERDICT alone is not independent evidence of detection -- only the exact-location
match is, and that part is audit-confirmed not leak-derived.

Trace file: [`o3_TP_r4r_ecdsa231.txt`](artifacts/traces/o3_TP_r4r_ecdsa231.txt). Eval log:
`logs_pilot/2026-07-12T19-19-32+00-00_..._CrWDekaMctfRrHpAHxfZRB.eval`.

### C3. opus-4.6 remains unbounded above 896 ops for N50; N90 > 448 well-established, N90 > 896 NOT established

100% at N=231 (2/2), 100% at N=448 (pooled 44/44: 42 parent + 2 pilot), 100% at N=896 (1/1, this
pilot's most expensive single call at $4.75). No logistic fit is possible (all-100% -> MLE diverges);
this is a lower bound on N50, not a measurement of it.

**N90 implication, with the same statistical-power reasoning as C2.** The N=448 point is well-powered
(n=44): if opus's true reliability there were only 90% rather than ~100%, the chance of all 44 samples
succeeding is `0.9^44 ~= 0.97%` (recomputed here) -- under 1%, so 44/44 is strong evidence the true rate
is genuinely close to 100%, well above the 90% threshold. **N90 > 448 ops is well-established.** The
N=896 point is a **single tampered sample (n=1, not n=2 -- one genuine TN plus one tampered TP_r4r
make up the 2 total calls in that batch, but reliability is defined on the tampered rate alone)**: if
the true rate there were exactly 90%, the chance of that one sample succeeding anyway is `0.9^1 = 90%`
-- essentially no statistical power to distinguish "genuinely >=90% reliable at 896" from "genuinely
~50% reliable and got lucky once." **N90 > 896 is therefore NOT established by this data, in exactly
the same way N50 > 896 is not established** -- both rest on the identical single data point, which
cannot statistically distinguish a 51%-reliable process from a 99%-reliable one. The honest statement is
narrower than "opus remains unbounded": what is well-established is N90 > 448; N50 > 896 and N90 > 896
are both merely "not yet contradicted," carrying equal (and equally thin) evidential weight.

**Evidence: MEDIUM-STRONG on N50 > 896 and STRONG on N90 > 448; only WEAK on N90 > 896 specifically**,
for the reason above. The N=231 and N=448 points are well-supported (n=2 and n=44). The N=896 point
rests on a **single** tampered sample -- real and correctly scored, but thin, and the pilot deliberately
did not chase opus's exact crossing point further once the live grid's real-P-256 family was confirmed
as the better place to spend the next dollar of opus-4.6 budget (opus costs $2.253-2.377/call here and
the trend is rising with length).

**ECDSA-leak note:** the N=231 point folded into this pooled fit is opus's toy-ECDSA condition, which
carries the same renderer leak as C1/C2 above. The audit's location-metric result (not inflated) covers
all 38 pilot completions including opus's, but this report's author did not personally re-check the
leaked `v == r ?` line's value on opus's specific ECDSA-231 samples (no opus ECDSA trace file was pulled
for Deliverable 1) -- unlike C1/C2, this specific sample-level check was not independently redone here,
only the audit's aggregate claim is relied on for this point.

Trace files: [`opus46_TP_r4r_sha448.txt`](artifacts/traces/opus46_TP_r4r_sha448.txt),
[`opus46_TN_sha448.txt`](artifacts/traces/opus46_TN_sha448.txt),
[`opus46_TP_r4r_sha896.txt`](artifacts/traces/opus46_TP_r4r_sha896.txt). Eval logs:
`logs_pilot/2026-07-12T17-35-43+00-00_..._YkP4s2jTwqGFSZCCvzXi7h.eval`,
`logs_pilot/2026-07-12T19-07-58+00-00_..._iQ3kNd6qQct8HQZYhfvAjR.eval`.

### C4. gpt-4o's ECDSA failure mode is confident miscalibration, not disengagement

At N=231 (n=8: 4 genuine + 4 tampered), gpt-4o scored 0/8: **4/4 false positives** (called every
genuine trace TAMPERED) and **4/4 wrong-location** (called every tampered trace TAMPERED but named the
wrong line). Every response carried a specific, confidently-stated location and `p_tampered=1.00` --
inspecting the sampled false-positive completion directly (`gpt4o_FP_genuine_ecdsa231.txt`) shows the
model's visible reasoning walks through several header checks correctly, then asserts "Line 0114:
tampered value detected" with no shown derivation connecting that claim to anything wrong in the trace.
This is a different failure mode from the root SHA-256 experiment's SHA finding, where gpt-4o was largely
disengaged (near-zero reasoning effort, short refusal-shaped output). Zero UNPARSEABLE outcomes across
all 8 samples, so this is not a parsing artifact -- gpt-4o produced well-formed, on-schema output every
time; the content was simply wrong and confidently so.

**Neither N50 nor N90 is measurable for gpt-4o from this data** (0/4 at N=231, matching the parent's
0/42 at N=448 -- reliability is at or near 0% everywhere tested, so both thresholds are undefined
within the tested range, consistent with the locked prediction's direction if not its mechanism, see
"Prediction comparison" below).

**Evidence: STRONG, and sharpened rather than weakened by the ECDSA-leak audit finding.** The genuine
sample cited above (`gpt4o_FP_genuine_ecdsa231.txt`) has the leaked `v == r ?` line reading `True` --
a free, correct "GENUINE" signal was available in the trace text, and gpt-4o called it TAMPERED anyway.
This is not a case of the model exploiting a shortcut and still failing; it actively overrode an
available correct answer. The tampered sample cited (`gpt4o_TP_wrongloc_ecdsa231.txt`) has the leak
reading `False` (correctly indicating tampered), so that sample's TAMPERED verdict could in principle
have come from the leak, but the wrong-location naming is not explained by it either way -- the leak
carries no location information. n=8, unanimous 0/8, one representative completion directly inspected
and quoted above, structurally clean (no parse failures).

Trace files: [`gpt4o_FP_genuine_ecdsa231.txt`](artifacts/traces/gpt4o_FP_genuine_ecdsa231.txt),
[`gpt4o_TP_wrongloc_ecdsa231.txt`](artifacts/traces/gpt4o_TP_wrongloc_ecdsa231.txt). Eval log:
`logs_pilot/2026-07-12T19-19-28+00-00_..._VW9e5sVkMMpzZWeCKUK7cG.eval`.

### Prediction comparison (against the locked table above)

| Prediction | Locked confidence | What the pilot found | Held? |
|---|---|---|---|
| gpt-5 N50 ≈ 470-550 | Medium | N50 ~= 448 (real 3-point fit) | **Close, roughly held** -- 448 is ~5% below the predicted low end, same order, same direction |
| o3: won't clear 50% at any tested rung (engagement-floor framing) | High on direction | o3 scored 100% (4/4) at N=231 -- clearly clears 50% | **MISSED.** o3 is a real bracket (231, 448), not a floor; the mechanism ("engagement floor") also doesn't match -- o3 engaged and succeeded at the short rung, then failed completely at the long one, a capacity limit, not disengagement |
| gpt-4o: won't clear 50% at any tested rung (engagement-floor framing) | High on direction | 0/8 correct at N=231 -- direction (won't clear 50%) held | **Direction held, mechanism missed.** Pilot data shows active, confident, wrong engagement (C4 above), not the predicted disengagement/floor behavior |
| opus-4.6 N50 ≈ 10,000-30,000 | Low | Still 100% at N=896 (far below the predicted range) | **Open, not yet contradicted or confirmed** -- no data above 896 ops exists for opus yet |
| gpt-5.5 N50 ≈ 2,000-3,000 | Medium | Not tested in this pilot | **Open** -- only the parent's single N=448 point (88%) exists |
| SHA-vs-ECDSA overlay/divergence at matched op count | Low-Medium (prior: near-overlay) | **Not actually testable from this pilot's data** -- the models run on both families (gpt-5, opus-4.6) were tested at DIFFERENT op counts per family (ECDSA-231 vs. SHA-448/896), not a matched op count | **Open, no real comparison ran** -- this needs its own matched-length rungs, deferred to the live grid |
| Doubling time 2-4 months, ECDSA-band crossing 2027-2028 | Low | Not testable without gpt-5.5 data or opus-4.6's real crossing point | **Open** |

**N90 note:** the locked predictions table (above) only ever covered N50; N90 was added to this report
after the predictions were locked, per Ram's later request, so there is no locked N90 prediction to
compare against. See "N50 vs. N90" above for the new N90 numbers themselves.

---

## Cost ledger

**Total: $20.37 of the $45 pilot cap** (per-file amounts sum to $20.35; the $0.02 gap is per-file cent
rounding in the printed table below, not a data error -- `analyze_pilot.py`'s own running total, not
independently re-summed by hand, is the $20.37 figure).

| Family | Rung | Model | n | Input tok | Output tok | Reasoning tok | Cost | $/call |
|---|---|---|---|---|---|---|---|---|
| sha | n_blocks=1 (448) | openai/gpt-5 | 4 | 241,525 | 88,298 | 87,296 | $1.18 | $0.296 |
| ecdsa | bits=8 (231) | openai/gpt-5 | 4 | 21,696 | 66,090 | 65,152 | $0.69 | $0.172 |
| sha | n_blocks=1 (448) | anthropic/claude-opus-4.6 | 4 | 259,877 | 308,467 | 39,574 | $9.01 | $2.253 |
| ecdsa | bits=8 (231) | anthropic/claude-opus-4.6 | 4 | 23,848 | 91,650 | 21,246 | $2.41 | $0.603 |
| sha | n_blocks=2 (896) | anthropic/claude-opus-4.6 | 2 | 258,051 | 138,562 | 16,692 | $4.75 | $2.377 |
| sha | n_blocks=2 (896) | openai/gpt-5 | 4 | 479,765 | 61,411 | 60,544 | $1.21 | $0.303 |
| ecdsa | bits=8 (231) | openai/gpt-4o | 8 | 43,956 | 2,011 | 0 | $0.13 | $0.016 |
| ecdsa | bits=8 (231) | openai/o3 | 8 | 45,996 | 110,113 | 108,544 | $0.97 | $0.122 |

opus-4.6 is the binding cost constraint ($2.253-2.377/call at 448-896 ops, rising with length). gpt-4o is
by far the cheapest ($0.016/call, zero reasoning tokens) but produces the least useful data (C4 above).

**Call-count discrepancy, found while writing this report.** `README.md` and `plan.md`'s prose both
state "40 real model calls" / "8 real API batches (40 samples)". Directly counting samples across all
8 `logs_pilot/*.eval` files (`sum(len(log.samples) for each file)`) gives **38**, matching the sum of
the `n` column above (4+4+4+4+2+4+8+8=38). `inspect_ai`'s `ModelUsage` has no separate call/request
count distinct from sample count, and no retries or multi-turn tool calls are present in any log (every
sample is exactly one user message + one assistant message), so there is no hidden mechanism that would
make "40" and "38" both correct readings of the same data. **This report uses 38, the number recounted
directly from the logs; `README.md` and `plan.md`'s "40" should be corrected.** Flagged to the team
lead in the accompanying message rather than silently edited here, since those are files this report's
author (frontier-report) did not build.

**Filename-vs-model false-friend, noted so a future reader doesn't repeat the mistake made while
writing this report:** the file `logs_pilot/2026-07-12T18-09-23+00-00_verification-frontier_
o3KiXC2fmfWUyY9aQrUsVd.eval` contains **anthropic/claude-opus-4.6** data (the toy-ECDSA bits=8
condition), not o3 data -- `o3KiXC2fmfWUyY9aQrUsVd` is Inspect's random per-run task ID, unrelated to
the model name. The actual o3 data lives in the differently-named
`2026-07-12T19-19-32+00-00_..._CrWDekaMctfRrHpAHxfZRB.eval`.

---

## Runs table

Every `.eval` file in `logs_pilot/`, one row each, reconciled against a direct sample count.

| # | File | Family / rung | Model | n | Outcomes | Cost |
|---|---|---|---|---|---|---|
| 1 | `2026-07-12T17-24-09+00-00_..._mtNjJTEWYYiNzzD9xgn7aS.eval` | sha / n_blocks=1 | gpt-5 | 4 | TN=2, FN=2 | $1.18 |
| 2 | `2026-07-12T17-32-07+00-00_..._Cg4xhDmme3cF6xy7YaN7yW.eval` | ecdsa / bits=8 | gpt-5 | 4 | TN=2, TP_r4r=2 | $0.69 |
| 3 | `2026-07-12T17-35-43+00-00_..._YkP4s2jTwqGFSZCCvzXi7h.eval` | sha / n_blocks=1 | claude-opus-4.6 | 4 | TN=2, TP_r4r=2 | $9.01 |
| 4 | `2026-07-12T18-09-23+00-00_..._o3KiXC2fmfWUyY9aQrUsVd.eval` | ecdsa / bits=8 | claude-opus-4.6 (see filename note above) | 4 | TN=2, TP_r4r=2 | $2.41 |
| 5 | `2026-07-12T19-07-58+00-00_..._iQ3kNd6qQct8HQZYhfvAjR.eval` | sha / n_blocks=2 | claude-opus-4.6 | 2 | TN=1, TP_r4r=1 | $4.75 |
| 6 | `2026-07-12T19-08-09+00-00_..._eAeh2AnN4SFXjEKWiEUUTT.eval` | sha / n_blocks=2 | gpt-5 | 4 | TN=2, FN=2 | $1.21 |
| 7 | `2026-07-12T19-19-28+00-00_..._VW9e5sVkMMpzZWeCKUK7cG.eval` | ecdsa / bits=8 | gpt-4o | 8 | FP=4, TP_wrong_loc=4 | $0.13 |
| 8 | `2026-07-12T19-19-32+00-00_..._CrWDekaMctfRrHpAHxfZRB.eval` | ecdsa / bits=8 | o3 | 8 | TN=4, TP_r4r=4 | $0.97 |

**Reconciliation: 8 logs on disk in `logs_pilot/`, 38 sample rows total** (4+4+4+4+2+4+8+8), zero
UNPARSEABLE outcomes anywhere, cost column sums to $20.35 (vs. `analyze_pilot.py`'s own printed
$20.37 total -- a 2-cent per-file-rounding gap, not a missing row). No file failed to read with the
currently-installed `inspect_ai` (0.3.189) -- the `extra_body` fix for `reasoning_effort="max"`
(Design decisions table, above) means every log, including opus-4.6's, is fully readable via
`read_eval_log()`; none needed a zipfile+raw-json fallback.

---

## Reproducibility

```
cd experiments/260706-credible-deals-polish/verification-frontier

# Self-tests (zero API calls, zero cost, ~1-2 min):
python3 stage0_selftest.py        # expect "0 failures across all self-tests"
python3 score_frontier.py         # scoring-rule self-test

# Token dry run (zero API calls):
python3 token_dry_run.py

# Analysis of the ALREADY-COLLECTED pilot logs (zero new API calls, pure
# local computation -- every per-condition outcome, cost, and logistic fit
# number in this report's Claims/Cost-ledger sections is this script's
# literal stdout, reproduced by running it):
python3 analyze_pilot.py

# This report's trace extraction (zero new API calls, reads logs_pilot/*.eval
# directly; regenerates every file in artifacts/traces/):
python3 extract_traces.py
```

**Replaying the pilot's real API calls would cost real money again** (Inspect's cache key includes
model + prompt + every `-T` param; rerunning the exact `inspect eval` commands in `README.md`'s
Reproduce block makes NEW paid calls unless every parameter matches an existing cache entry). No
`--assert-cached` free-replay path exists for this harness yet since the pilot was the first live run
of it. The three commands above (`stage0_selftest.py`, `analyze_pilot.py`, `extract_traces.py`) are the
free, zero-new-spend path to verify everything in this report.

---

## Limitations

- **ECDSA renderer leaked the verdict (CRITICAL-but-contained, see "Independent adversarial audit"
  above).** The final `v == r ?` line in every toy-ECDSA trace leaks the binary GENUINE/TAMPERED answer
  directly (~98.7% of the time; the toy-field coincidence accounts for the rest). **Every ECDSA
  VERDICT-level number in this report (TN/FP classification specifically) is confounded and should be
  read as location-metric-only valid.** The r4r location metric that every STRONG-tagged ECDSA claim
  above (C1, C2, part of C3, C4) actually relies on is independently audit-confirmed NOT inflated by
  this leak (~0.4% blind-guess rate over 231 lines; all 38 completions re-scored and matched exactly).
  A renderer fix is in progress; post-fix runs will carry a version marker so pre-fix and post-fix
  ECDSA data are never silently pooled. SHA claims are entirely unaffected (no equivalent leak exists
  there).
- **Non-adversarial tampers and uncapped CoT** (stated at the top of Claims) apply to every number in
  this report; treat all reliability figures as upper bounds on real-world verification robustness.
- **Two families only.** Real P-256 fragments, report-shaped SHA payloads, and the composite
  mini-attestation rung are built and self-tested but never called a real model in this pilot -- every
  claim above is scoped to toy-field ECDSA and multi-block SHA.
- **gpt-5.5 has zero pilot-native data.** Every gpt-5.5 number anywhere in this project comes from the
  parent run (root SHA-256 experiment) (a single N=448 point, 88%), not from this pilot.
- **opus-4.6's N=896 point is n=1.** A single sample, correctly scored, but not enough to distinguish
  "opus is genuinely unbounded up to 896" from "opus got lucky once" with any statistical confidence
  (recomputed: if the true rate there were only 90%, a single success still occurs 90% of the time --
  essentially zero power). N90 > 448 IS well-established (n=44, `0.9^44 ~= 1%` under the null of a true
  90% rate); N90 > 896 and N50 > 896 are both merely "not yet contradicted," not "established," and rest
  on the identical thin data point -- see C3 for the full statistical-power argument.
- **N90's ratio to N50 is model-specific, not a fixed conversion.** The theoretical `(1-p)^N` model
  predicts N90 ~= 0.15 x N50; gpt-5's one real fit instead measures N90 ~= 0.86 x N50 (see "N50 vs. N90"
  under Claims). Do not apply either ratio to o3, opus-4.6, or gpt-5.5 without a real fit for that model
  specifically -- the live grid's larger n is what will supply those fits.
- **No matched-op-count SHA-vs-ECDSA comparison ran.** The overlay/divergence question `proposal.md`
  poses as the headline deliverable was not actually tested by this pilot's rung choices.
- **OpenAI reasoning content is not inspectable** for gpt-5/o3/gpt-4o through this pilot's collection
  path (encrypted blob or absent, see the third honesty caveat under Claims) -- any claim about WHY
  these models fail, beyond what their visible output states, is not evidenced here.
- **Confidence intervals are not reported for any fit.** Bootstrap CIs need more samples per rung than
  this pilot's n=2-8 per condition provides; the live grid's larger n is designed to fix this.
