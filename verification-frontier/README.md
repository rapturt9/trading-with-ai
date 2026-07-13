# Verification frontier: how long a cryptographic trace can a model verify?

**What this measures.** A model's ability to catch a single planted error in a computation trace has a length limit. This experiment measures that limit as N50, the number of word-level cryptographic operations at which a model's tamper-detection reliability crosses 50%, and asks whether N50 is growing fast enough across model release dates to reach real signature-verification scale (NIST P-256 ECDSA, roughly 410k-800k operations) on a predictable schedule. It is the horizon experiment behind Figure 3 of the LessWrong post "Making credible deals with AIs" by Ram Potham (link added when the post is live).

This folder is part of the standalone reproducibility package for that post. It extends the root SHA-256 tamper experiment (at the repository root) with multi-block SHA-256, real NIST P-256 ECDSA, and composite attestation traces. Two internal working notes it refers to by name, `proposal.md` (the pre-registered design) and `plan.md` (the append-only run log), are private and are not included in this public package; where the text points to them, the fuller detail lives there, while the code, logs, and results in this folder stand on their own.

Stage 0 / 0c (zero API calls) of a METR-style time-horizon experiment: how many word-level cryptographic operations can a model reliably tamper-check in one trace, and does that number grow fast enough to reach real signature-verification scale (real P-256 ECDSA, ~410k-800k operations) on a predictable schedule.

# Result

**Stage 0/0c only. No model has been called; no N50 has been measured yet.** Five trace-generator families, all built by extending, not duplicating, the already-shipped `../sha256_trace.py`:

1. **Multi-block SHA-256** -- real Merkle-Damgard chaining, dual and decimal-densified rendering.
2. **Toy-field ECDSA** -- a small constructed elliptic curve (8/12/16-bit prime field), the full ECDSA verification algorithm at word-scale precision. Secondary comparison family (was the first-built design; superseded as the PRIMARY family by #3 below on Ram's later correction).
3. **Real P-256 verification fragments (PRIMARY family, Stage 0c)** -- real NIST P-256 curve constants, the general Weierstrass `a`-term reinstated (`a = p-3`, not the `a=0` shortcut family #2 uses), a contiguous 1/2/4/8-operation span drawn from a genuine, complete signature verification, every multiplication linearly decomposed (not pointwise) into word-scale checkable lines.
4. **Report-shaped SHA payloads (Stage 0c)** -- family #1's exact machinery, reused via a `message=` override, hashing a labeled attestation-report-style message instead of random bytes.
5. **Composite mini-attestation (Stage 0c)** -- families #3 and #4 chained into one trace (hash a report, verify a real P-256 signature over its digest), the closest this project gets to the real TEE-attestation mechanism.

Every family's tamper mechanism (SHA: addition/bitwise/schedule-word; toy and real ECDSA: a unified line-level mechanism covering addition/multiplication/reduction/inverse-check; composite: either half, weighted by real line count) is proven to leave exactly one locally-inconsistent line in a tampered trace and zero in a genuine one. Every family is cross-checked against an independent ground truth: `hashlib.sha256` for SHA, and a from-scratch Jacobian-coordinate reference verify (different coordinate system, different inverse method) for both ECDSA families, now confirmed at REAL 256-bit curve scale for family #3, not just toy scale.

**Self-test sweep (`stage0_selftest.py`'s default 5 seeds): 0 failures** across all 5 families, every rung, every position bucket, every tamper mechanism -- see the Reproduce block below for the exact command and expected output.

**Design notes, in order:** (1) the toy-field ECDSA family was redesigned mid-session on Ram's correction (toy-scale the field, not the scalar against a real 256-bit field; trace the full verification algorithm; no point-granularity lines) -- see `plan.md`'s "ECDSA family redesigned" entry. (2) Stage 0c added the real P-256 family as primary, a linear (not pointwise) multiplication-decomposition rule, and the two composite families -- see `plan.md`'s "Stage 0b"/"Stage 0c" entries, including a real bug the P-256 self-test sweep caught (an earlier version paired ladder doublings/adds per BIT independently in two functions; stopping mid-bit-pair silently dropped a pending operation -- fixed by having both functions walk one shared flat operation sequence).

**Pilot: RUN, $20.37 of the $45 cap, 38 real model calls (corrected 2026-07-12 -- the independent report-agent recount caught a math error: 4+4+4+4+2+4+8+8 across the 8 `.eval` files = 38, not the 40 first stated here), zero parse failures.** `inspect_task_frontier.py` (SHA/toy-ECDSA families 1-2) plus `score_frontier.py` (generalizes the root SHA-256 experiment's right-for-right-reason rule to a 3-part exact location, not just a round). Real per-call cost: gpt-5/o3/gpt-4o all under $0.31/call; opus-4.6 $2.25-2.38/call, matching the root SHA-256 experiment's historical rate despite this harness's leaner JSON schema (inspecting the actual completions showed opus's visible output was short and well-formed -- the cost is real thinking, not runaway visible text). Findings: gpt-5's detection decays cleanly 100%->50%->0% across N=231/448/896 ops (joint fit N50~=448); o3 is a clean bracket, 100% at N=231 and 0% at N=448 (crossing point not further localized by 2 rungs); opus-4.6 remains saturated at 100% through N=896, still an unbounded lower bound; gpt-4o on ECDSA is NOT floor-disengaged like on SHA -- it actively engages but calls every trace TAMPERED (4/4 false positives on genuine), a distinct failure mode worth its own note. Full per-condition table, the joint logistic fits, and the live-grid cost projection are in `plan.md`'s "Pilot RUN" entry (private working note); this file states only what's publicly reportable. Found and fixed one structural bug before any spend: the installed `inspect_ai`'s `GenerateConfig.reasoning_effort` rejects `"max"` (a closed Pydantic Literal), which also explains why 4 old opus/fable-5 `.eval` logs in `../logs_inspect_checkable/` are unreadable with the current library version -- fixed by routing `"max"` through `extra_body` instead.

**Post-pilot audit finding (verdict leak, ECDSA rows only), found and FIXED same evening: `location-metric-only` for the pre-fix data.** `ecdsa_trace.py`'s toy-field renderer (the only ECDSA family this pilot called) printed the genuine/tampered verdict directly as its last line (`v == r ? {valid}`). Per an independent re-scoring, the exact-location `TP_r4r` numbers above are NOT inflated (naming the precise corrupted line isn't derivable from a leaked boolean), but every OTHER verdict-level number from the pre-fix runs (TN, FP, any GENUINE/TAMPERED accuracy not requiring exact location) is confounded and is not reported as verification evidence anywhere in this experiment. Confirmed by direct code inspection that the real-P-256 and composite renderers (Stage 0c) never shared this leak. Fixed: the leaked line is deleted (the model must now do the comparison itself from the separately-printed `v` and `r`), all three renderer modules carry a `RENDERER_VERSION` marker so pre/post-fix data is never mixed, self-test re-run clean. Live-grid ECDSA/toy-field/P-256/composite conditions, paused during the fix, have resumed -- see `plan.md`'s dated audit entry for the full ruling.

**Live grid: MVP SHIPPED, $53.38 total (pilot + live grid, both well inside their caps).** Measured N50 (50%-reliability trace length) and N90 (90%-reliability, the deployment-relevant threshold per Ram: a 50%-reliable verifier launders fakes, since a wrongly-passed check makes an AI MORE confident in a fabrication) fit SEPARATELY per model and per family group (toy: SHA + toy-field ECDSA; real: P-256 fragments), not pooled -- pooling broke for o3 (produced a nonsensical negative-width bracket) because toy and real genuinely do NOT overlay: real curve arithmetic is measurably harder than toy at matched-or-shorter operation count, for both o3 and gpt-5. This is the proposal's own pre-registered "divergence" alternative, confirmed with real data, not assumed going in. Results: **gpt-5** has a real fitted crossing, N50~=448 ops (90% CI [25,459], wide -- honestly reported, not smoothed), N90~=415 ops (CI [24,422]); **o3** is bracketed (321,448) ops on toy data, with real-P-256 data showing it's already at 0% detection by N=202-270 (lower than the toy bracket); **claude-opus-4.6** stayed saturated at 100% through every toy/SHA rung tested (up to 896 ops) and only dropped to 0% on real P-256 at N=2024-2092, giving a coarse cross-family bracket (896, 2024) -- the first real evidence bounding opus's N50 after this whole project's back-calculated estimate was flagged as implausibly high; **gpt-4o** stays a floor (0% everywhere, both families, not length-driven). One apparatus failure disclosed, not averaged in: opus-4.6's P-256 n_ops=4 run was 4/4 UNPARSEABLE, verified via `stop_reason=max_tokens` at exactly the 128,000-token cap with zero visible output (a real completion-cap failure, matching this model's documented historical pattern, not a detection-reliability signal) -- excluded from the fit; the clean n_ops=8 rung is the real opus data point. `verification_horizon_measured.png` (this folder) is the dual-horizon plot: N50/N90 points and brackets vs. release date, TEE/ECDSA bands, and the trend-line crossing dates (extrapolation from 3 non-floor models, labeled honestly as mostly-bracket data). Full numbers, the toy-vs-real divergence finding, and two structural bugs found and fixed mid-launch (an `inspect eval` task-discovery race caused by a blocking git subprocess call colliding with this vault's autosync cron; a payload-conflation bug in the analysis script) are in `plan.md`'s "LIVE GRID MVP" entry. Composite mini-attestation rung, denser opus/o3 brackets, and the 8-vs-16-bit micro-task are explicitly deferred post-MVP, not run.

The live grid ($250-500, hard cap $600) is pre-authorized (Ram, via the team lead) effective on this pilot report plus Stage 0c's self-tests, both now true -- SHA-family rungs starting now; ECDSA/P-256/composite rungs paused pending the verdict-leak fix above. Priority once resumed: real-P-256 fragment rungs (family 3, now PRIMARY) and report-shaped SHA rungs first, sized to bracket each model's N50; the toy-vs-real matched-length comparison; the composite mini-attestation rung; the 8-vs-16-bit addition micro-task.

# Reproduce

```
# 1. This is vault-native, not a separate repo -- cd into this folder.
cd verification-frontier

# 2. Setup: needs the repo-root files present (imported via
#    sys.path, not vendored) and tiktoken/numpy/scipy (already in this
#    vault's environment; nothing else to install).

# 3a. Run every self-test (all 5 generator families) across the full seed x
#     rung x bucket x class sweep, and regenerate the example artifacts.
#     Zero API calls, zero cost, ~1-2 minutes (P-256 fragment generation
#     at n_ops=8 is the slowest single piece).
python3 stage0_selftest.py
# Expect: "=== TOTAL: 0 failures across all self-tests ===" and
# "Wrote artifacts/selftest_summary.txt (0 failures)".

# 3b. Individual module self-tests (each module's own __main__, a smaller,
#     faster single-seed check -- stage0_selftest.py is the authoritative
#     sweep, these are for iterating on one module):
python3 sha256_multiblock.py
python3 sha256_tamper_classes.py
python3 ecdsa_trace.py
python3 p256_trace.py
python3 report_payload.py
python3 mini_attestation.py

# 3c. Token dry run: exact token counts per rung, every rendering, every
#     family, and which of the 5 live-run models' context windows each
#     rung fits. Zero API calls, ~1-2 minutes.
python3 token_dry_run.py

# 4. View outputs
# artifacts/selftest_summary.txt          -- full self-test log (0 failures)
# artifacts/example_sha_1block_genuine.txt / _tampered.txt
# artifacts/example_sha_8block_genuine_excerpt.txt
# artifacts/example_sha_2block_decimal_densified_excerpt.txt
# artifacts/example_ecdsa_genuine.txt / _tampered.txt        -- 8-bit toy field
# artifacts/example_ecdsa_12bit_genuine_excerpt.txt
# artifacts/example_p256_genuine.txt / _tampered.txt         -- real P-256, n_ops=2
# artifacts/example_report_payload_genuine.txt
# artifacts/example_composite_genuine.txt / _tampered.txt
# (stdout of token_dry_run.py; not saved to a file, rerun to view -- it's
#  a zero-cost computation, not worth caching)

# 5. Pilot (REAL money, $20.37 already spent -- these commands, if rerun,
#    make NEW paid API calls since Inspect's cache key includes model+prompt
#    and every -T param; they do NOT replay the existing logs_pilot/*.eval
#    for free unless every parameter matches exactly, in which case Inspect's
#    native cache (cache=True in the task) replays for $0).
#    Requires OPENROUTER_API_KEY in the environment (export it, or source your own env file).
export OPENROUTER_API_KEY=...

# SHA family (rung = n_blocks, 448 ops/block):
inspect eval inspect_task_frontier.py --model openrouter/openai/gpt-5 \
    -T family=sha -T model_key=openai/gpt-5 -T rung=1 -T n=4 --log-dir logs_pilot
inspect eval inspect_task_frontier.py --model openrouter/anthropic/claude-opus-4.6 \
    -T family=sha -T model_key=anthropic/claude-opus-4.6 -T rung=1 -T n=4 --log-dir logs_pilot
inspect eval inspect_task_frontier.py --model openrouter/openai/gpt-5 \
    -T family=sha -T model_key=openai/gpt-5 -T rung=2 -T n=4 --log-dir logs_pilot
inspect eval inspect_task_frontier.py --model openrouter/anthropic/claude-opus-4.6 \
    -T family=sha -T model_key=anthropic/claude-opus-4.6 -T rung=2 -T n=2 --log-dir logs_pilot

# Toy-field ECDSA family (rung = field bits, 231 ops at bits=8):
inspect eval inspect_task_frontier.py --model openrouter/openai/gpt-5 \
    -T family=ecdsa -T model_key=openai/gpt-5 -T rung=8 -T n=4 --log-dir logs_pilot
inspect eval inspect_task_frontier.py --model openrouter/anthropic/claude-opus-4.6 \
    -T family=ecdsa -T model_key=anthropic/claude-opus-4.6 -T rung=8 -T n=4 --log-dir logs_pilot
inspect eval inspect_task_frontier.py --model openrouter/openai/gpt-4o \
    -T family=ecdsa -T model_key=openai/gpt-4o -T rung=8 -T n=8 --log-dir logs_pilot
inspect eval inspect_task_frontier.py --model openrouter/openai/o3 \
    -T family=ecdsa -T model_key=openai/o3 -T rung=8 -T n=8 --log-dir logs_pilot

# Analysis (zero new cost, reads logs_pilot/*.eval + logs_live/*.eval +
# the parent's results_checkable.jsonl): per-condition outcomes, real cost from
# token usage x live OpenRouter prices, and the N50/N90 logistic fits,
# fit SEPARATELY per model x family-group (toy vs real-P-256) with
# bootstrap CIs and apparatus-failure exclusion (see plan.md's "LIVE GRID
# MVP" entry for why pooling toy+real broke for o3).
python3 analyze_pilot.py

# 6. Live-grid MVP conditions (REAL money, ~$33 already spent, live-grid
#    cap $600 -- rerunning makes NEW paid calls unless every -T param and
#    the log-dir match an existing logs_live/*.eval exactly, in which case
#    Inspect's native cache replays for $0). Requires OPENROUTER_API_KEY.
# Real P-256 fragment family (rung = n_ops: 1/2/4/8 contiguous point ops):
inspect eval inspect_task_frontier.py --model openrouter/openai/gpt-5 \
    -T family=p256 -T model_key=openai/gpt-5 -T rung=4 -T n=8 --log-dir logs_live
inspect eval inspect_task_frontier.py --model openrouter/anthropic/claude-opus-4.6 \
    -T family=p256 -T model_key=anthropic/claude-opus-4.6 -T rung=8 -T n=4 --log-dir logs_live
# (see plan.md's "LIVE GRID MVP" entry for the full set of -T rung/-T n
# combinations actually run across all 4 models)

# Dual-horizon plot (N50 + N90 vs release date, TEE/ECDSA bands, trend
# lines): reads a frozen snapshot of analyze_pilot.py's fit output
# (hardcoded in the script itself, not re-fit live -- see the script's
# docstring for why, and plan.md for the exact analyze_pilot.py run this
# snapshot came from). Zero new API calls.
python3 make_ops_horizon_plot_v2.py
# Writes: verification_horizon_measured.png
```

**Note on the parent extension.** `stage0_selftest.py` and every module here import from `../sha256_trace.py`, which this work extended with four backward-compatible keyword arguments (`compress(init_state=, start_round=)`, `render_dual(binary_state=, tag_op_types=)`). Re-running the parent's own self-test (`cd .. && python3 sha256_trace.py && python3 stage0_render.py`) after the extension reproduces byte-identical output to what's already committed there (`git diff --stat -- artifacts/` is empty) -- the extension is additive, nothing existing changed behavior.

# Evidence

- `artifacts/selftest_summary.txt`: the full self-test log, every family x rung x bucket x class combination, 0 failures.
- `artifacts/example_sha_1block_genuine.txt`, `example_sha_1block_tampered.txt`: a complete rendered 1-block SHA-256 trace pair (dual rendering), the tampered one with its exact `local_consistency_report` printed in the header.
- `artifacts/example_sha_8block_genuine_excerpt.txt`: the length-scaling axis at its largest self-tested rung (3,584 operations), excerpted for human inspection (the full trace is verified programmatically in the sweep, not by reading this excerpt).
- `artifacts/example_sha_2block_decimal_densified_excerpt.txt`: the decimal-densified rendering that buys length reach, excerpted.
- `artifacts/example_ecdsa_genuine.txt`, `example_ecdsa_tampered.txt`: a complete toy-field ECDSA verify trace pair (8-bit field, `Curve(p=223, n=229)`), the tampered one flagged at exactly one line (`ladder2 op 2 y3`), hand-checkable: `(138 - 183) mod 223 = 178`, printed value `162`.
- `artifacts/example_ecdsa_12bit_genuine_excerpt.txt`: the 12-bit rung (417 op lines, closest match to SHA's one-block op count), excerpted.
- `artifacts/example_p256_genuine.txt`, `example_p256_tampered.txt`: a complete real P-256 verification-fragment trace pair (n_ops=2, real 256-bit curve), the tampered one flagged at exactly one line.
- `artifacts/example_report_payload_genuine.txt`: a labeled attestation-report-style message (`MEAS=... NONCE=... TS=... FILL=...`) hashed via the exact SHA family machinery.
- `artifacts/example_composite_genuine.txt`, `example_composite_tampered.txt`: the chained hash-then-sign trace, tampered one flagged at exactly one line across the whole composite.
- Token dry run (from `token_dry_run.py`, reproduced above): SHA dual rendering fits 1 block in every model's context budget and 2 blocks in all but gpt-4o; the decimal-densified rendering fits up to 4 blocks in all but gpt-4o. Toy ECDSA at every tested rung (231-556 op lines, 4,050-10,276 tokens) fits comfortably in every model's context window -- ~8x more token-efficient than SHA at a similar op count. Real P-256 fragments: 202/472/944/1,956 lines at n_ops=1/2/4/8, 10,142/23,377/46,513/96,052 tokens -- all fit every model except n_ops=8, which drops gpt-4o. The composite (report + P-256 fragment) ranges 73,551-156,265 tokens across p256_n_ops=1..8.
- `logs_pilot/*.eval` (4 files; 4 pre-verdict-leak-fix ECDSA logs moved to `logs_pilot/prefix_leak_quarantine/`, see its README): the pilot's Inspect logs. `logs_live/*.eval`: the live-grid MVP's logs. Both readable via `inspect view` or `read_eval_log`; `analyze_pilot.py`'s output (per-condition outcomes, real costs, N50/N90 fits with bootstrap CIs) is computed directly from these, reproduced above.
- `verification_horizon_measured.png`: the dual-horizon (N50 + N90) plot, measured points/brackets vs. release date, TEE/ECDSA bands, trend-line crossing dates -- the live-grid MVP's headline deliverable.

# Changelog

- **2026-07-12 (Stage 0):** SHA multi-block + toy-field ECDSA generator families, tamper mechanisms, full self-test sweep (0 failures), token dry run. Zero API calls. **Dead ends:** the ECDSA family's first design (real 256-bit secp256k1 field, shortened scalar, point-granularity lines) was built, self-tested (0 failures), and then entirely replaced same-session on Ram's correction (toy-scale the field instead, trace the full verification algorithm at word-scale granularity) -- see `plan.md`'s "ECDSA family redesigned" entry; the v1 code and its self-test results are superseded, not carried forward.
- **2026-07-12 (Stage 0b):** locked the op-counting convention's linear (not pointwise) decomposition rule (`decompose_multiply_linear`, measured 4.0x line-count reduction on a real 256-bit multiply), SHA op-type line tagging, the headline overlay/divergence plot design, and the Roadmap section. Found (and correctly handled, not hard-coded wrong) that header-section ECDSA tampers algebraically preserve curve membership.
- **2026-07-12 (Stage 0c):** added real P-256 verification fragments as the PRIMARY family (real curve constants, general `a`-term, `traced_mulmod`'s linear multiplication decomposition, contiguous fragments drawn from a genuine complete verification), report-shaped SHA payloads, and the composite mini-attestation chaining both. Fixed a real bug the self-test sweep caught: an earlier fast-forward/fragment pairing paired doublings/adds per bit independently in two functions, silently dropping a pending operation when a fragment started mid-bit-pair; fixed by having both functions walk one shared flat operation sequence. **Dead ends:** none new -- the multiplication-limb tamper mechanism from Stage 0/0b was superseded by `traced_mulmod`'s integration into the P-256 formulas rather than wired in separately.
- **2026-07-12 evening (Pilot):** `inspect_task_frontier.py` + `score_frontier.py` built (Inspect task, families 1-2, exact-location r4r scoring). Fixed a structural bug before any spend: `inspect_ai`'s `GenerateConfig.reasoning_effort` rejects `"max"`, routed through `extra_body` instead. Ran 8 real API batches (38 samples, corrected from an earlier miscounted 40), $20.37 of the $45 cap, zero parse failures. Findings: gpt-5's decay cleanly brackets N50~=448; o3 brackets to (231,448) but 2 rungs don't further localize it; opus-4.6 saturated at 100% through N=896, still unbounded; gpt-4o on ECDSA engages but with a strong false-TAMPERED bias, a different failure mode than its SHA disengagement. Mid-pilot design escalations from Ram (real P-256 as PRIMARY family, TEE-attestation-realism items, at-least-3-measured-points requirement) folded into `proposal.md`, not built mid-pilot -- `frontier-builder` built and self-tested them in parallel (Stage 0c). Full numbers in `plan.md`'s "Pilot RUN" entry. **Dead ends:** none -- every probe produced usable data; stopped chasing opus-4.6's exact N50 in the pilot once the live grid's real-P-256 family was confirmed as the better place to spend that budget.
- **2026-07-12 late evening (verdict-leak fix + live-grid MVP):** `frontier-builder` found and fixed a verdict leak in the toy-field ECDSA renderer (deleted the leaking comparison line; P-256/composite renderers audited clean; `RENDERER_VERSION` marker added to all three). Live-grid MVP shipped per Ram's fast-MVP directive: P-256 family wired into the harness (2-part location scoring, `prompt_template_frontier_p256.md`), report-shaped SHA parity batch run across all 4 models, real-P-256 rungs run across gpt-4o/o3/gpt-5/opus-4.6. $53.38 total spend (pilot + live). Headline finding: toy-field and real-P-256 do NOT overlay (fitting them pooled produced a nonsensical bracket for o3; splitting by family group revealed real curve arithmetic is measurably harder at matched-or-shorter op count) -- the proposal's pre-registered "divergence" answer, confirmed with data. Measured N50/N90 for gpt-5 (real fit + CI), o3 and opus-4.6 (brackets); opus-4.6's N50 is bounded for the first time in this project (896, 2024), replacing its earlier implausible back-calculated estimate. **Dead ends:** none in the shipped data -- composite rung, denser opus/o3 sampling, and the 8-vs-16-bit micro-task were explicitly deprioritized post-MVP, not attempted and abandoned. Two structural bugs found and fixed mid-launch (an `inspect eval` task-discovery race from a blocking git subprocess call colliding with this vault's autosync cron; a payload-conflation bug in `analyze_pilot.py`'s grouping key) -- see `plan.md`'s "LIVE GRID MVP" entry for both.

# Children
None.
