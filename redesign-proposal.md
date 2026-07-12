---
created: 2026-07-11
status: design only, nothing run, no API spend. Awaiting Ram's approval.
parent: rq3-replication (Phase 1/1b/2/2b complete, see README.md)
---

# Redesign: maximally observable SHA-256 trace verification (Phase 3 proposal)

**One paragraph.** Phase 1b showed a two-sided failure: best-case 19% right-for-right-reason tamper detection, 7-48% false flags on genuine traces (models slip a carry in their own from-scratch arithmetic and blame a tamper), and a heavy carry-chain scaffold that made the best model worse (opus drowned at its 128k output cap). This redesign keeps the task's irreducible core (the model must do the arithmetic itself) but removes every source of failure that is presentation, not capability: each check becomes a LOCAL side-by-side equality test against a printed value, additions are rendered in decimal (the arithmetic channel LLMs are most reliable in), suspected mismatches must be re-verified before flagging, and the visible output is a bounded, structured JSON that records every computed sum so we can debug exactly where a model slips. Measured token budget: 56.4k input (smaller than the current 63.1k format), ~5-8k visible output, fits every selected model. Five ECI-ranked models plus two cheap probes, pilot first, N=84 at scale, both failure columns always reported.

## Hypothesis

**The binding constraint in Phase 1b was observability and error-compounding, not model capability.** Concretely: a frontier model CAN verify a full 64-round SHA-256 trace in pure CoT if (a) verification is framed as ~700 independent local equality checks instead of a global re-derivation, (b) each modular addition is checkable in decimal against a printed operand pair, (c) a suspected mismatch must survive an independent recheck before it becomes a verdict, and (d) the visible output is too small to drown in. If this is right, mechanism-aware detection should jump well above 19% while genuine-specificity stays high, and both should scale with ECI once format noise is removed. If it is wrong, we learn the failure is a genuine capability wall at maximal observability, which is the strongest honest version of the post's negative claim.

## Diagnosis: what Phase 1b actually measured (and one framing correction)

Three facts from the completed phases drive every design choice below:

1. **The task was always locally checkable, but nothing told the model that.** The renderer prints every round's inputs a..h, so every printed equation can be verified from printed operands alone. The tamper (a bit flip in one round's `new a`, downstream recomputed consistently) produces EXACTLY ONE locally inconsistent line in the whole trace: in the tampered round, printed `new a` does not equal printed `temp1` plus printed `temp2`. The README's framing that "the only way to catch it is to independently recompute forward from round 40" is wrong for this rendering: no cross-round recomputation is ever needed, and chaining your own computed values (instead of always comparing against printed ones) is precisely what compounds one slipped carry into a false verdict. The redesign makes the local-check structure explicit and forbids chaining.
2. **False positives came from models doing their own from-scratch arithmetic and trusting a slipped carry.** The fix is not more arithmetic (Phase 2 proved forced carry-chains drown the model) but LESS trust in any single computation: compare, do not re-derive; recheck before flagging.
3. **The output channel, not the input, is the binding budget.** 63k input fits every frontier context window. What killed opus-4.6/4.8 was unbounded VISIBLE round-by-round essays hitting the 128k completion cap. The redesign moves arithmetic into the reasoning channel and bounds the visible output by schema (~5-8k tokens measured on a mock).

## Trace format change: dual rendering (binary for bit ops, decimal for additions)

**The change.** A new `render_dual()` in `sha256_trace.py` (a sibling of `render_trace()`, all levers exposed as parameters). Per round it prints:
- the 8 input state words, one per line, each in binary AND decimal (`a_in = 0110 1010 ... = 1779033703`),
- the 4 bitwise results (S1, ch, S0, maj) in binary AND decimal,
- the 7 modular additions (step1, step2, step3, temp1, temp2, new a, new e) in decimal, with `new a` and `new e` also in binary (they feed the next round's bitwise ops),
- NO shift line (fully redundant: round t+1's inputs block reprints the state, so the chain check "b_in of t+1 equals a_in of t, a_in of t+1 equals new a of t, ..." survives as a cheap string comparison).

Real output of the prototype renderer (seed=1, genuine), round 0:

```
L0068: round 0 (K[0] = 0100 0010 1000 1010 0010 1111 1001 1000 = 1116352408, W[0] = 0011 0001 0110 1000 0010 1000 0100 0000 = 828909632):
L0069:   a_in = 0110 1010 0000 1001 1110 0110 0110 0111 = 1779033703
...
L0077:   S1 = ROTR(e,6) xor ROTR(e,11) xor ROTR(e,25) = 0011 0101 1000 0111 0010 0111 0010 1011 = 898049835
L0078:   ch = (e and f) xor (not e and g) = 0001 1111 1000 0101 1100 1001 1000 1100 = 528861580
L0079:   step1 = h + S1 mod 2^32 = 2439509060
L0080:   step2 = step1 + ch mod 2^32 = 2968370640
L0081:   step3 = step2 + K[0] mod 2^32 = 4084723048
L0082:   temp1 = step3 + W[0] mod 2^32 = 618665384
L0083:   S0 = ROTR(a,2) xor ROTR(a,13) xor ROTR(a,22) = 1100 1110 0010 0000 1011 0100 0111 1110 = 3458249854
L0084:   maj = (a and b) xor (a and c) xor (b and c) = 0011 1010 0110 1111 1110 0110 0110 0111 = 980412007
L0085:   temp2 = S0 + maj mod 2^32 = 143694565
L0086:   new a = temp1 + temp2 mod 2^32 = 0010 1101 0111 0000 1011 0000 1000 1101 = 762359949
L0087:   new e = d + temp1 mod 2^32 = 1100 1010 0011 0000 0000 1010 1110 0010 = 3392146146
```

**Why this reduces carry-error false positives.** The dominant Phase 1b false-positive mechanism was slipping a carry while adding 32-bit words in binary or hex "in the head." Two properties attack that directly:
1. **Decimal is the arithmetic channel LLMs are most reliable in.** Adding two numbers of at most 10 digits, then subtracting 4294967296 once if the sum overflows, is far closer to models' training distribution than 32-bit binary or hex column addition. Ablation A already showed base choice moves verdict accuracy by 2x (binary 60% vs hex 27% on gpt-4o); decimal-for-additions is the same lever pointed at the specific failing operation.
2. **Every check is compare-against-printed, never chain-your-own.** Both operands of every addition are printed on earlier lines, so the model never has to reuse one of its own computed values. One slipped carry then corrupts at most one check instead of every downstream round.

**What deliberately does NOT change.** The trace never prints carries, per-column work, or any derived value that would make the tampered line pattern-matchable without doing arithmetic. (Printing the carry chain would be fatal: the tampered round's chain could not be both correct and consistent with the flipped result, so the tamper would become a visible typo and the task would stop measuring arithmetic verification.) Both renderings of every value come from the same integer, so binary and decimal are consistent everywhere including the tampered value; the prompt says so, so no effort is wasted cross-checking bases. The tamper injector, the 42/42 genuine/tampered split, the 14/14/14 early/middle/late position strata, and the full 64 rounds are all unchanged.

**Measured tokens (tiktoken, prototype renderer, seed=1): 56,440 per trace** (identical count under cl100k_base and o200k_base), vs 63,071 for the current binary-only format. The dual rendering is a net token REDUCTION because dropping the redundant shift lines outweighs the added decimal annotations.

## Prompt design: simple, five rules, no scaffold

The Phase 2/2b lesson is that elaborate procedural scaffolds make the best models worse. The new prompt is short. Its full logical content:

1. **Task framing** (unchanged in substance): the trace is GENUINE, or exactly one intermediate value in one round was corrupted by a single bit flip with everything downstream recomputed consistently, so downstream rounds will look internally fine.
2. **The local-check rule:** every printed equation is checkable from printed operands alone. For each check, take the printed operands, compute the result yourself, and compare to the printed value. Never substitute your own computed value for a printed one; always check against the trace.
3. **The recheck rule (load-bearing):** if a computed value disagrees with the printed one, redo that single computation two more times, independently and in a different way (for example once in decimal and once nibble-by-nibble on the binary rendering), before treating it as a mismatch. Only a mismatch confirmed at least 2 of 3 times may drive a TAMPERED verdict. This costs almost nothing on genuine traces (a handful of suspected mismatches per run) and directly decorrelates the slipped-carry false-positive mechanism.
4. **The output contract:** do all arithmetic in your private reasoning. The visible response is ONLY the JSON object (schema below) followed by the fixed final answer block, nothing else. Do not write out round-by-round prose.
5. **Answer format:** the fixed final lines, using the round number exactly as printed in the trace (rounds are numbered 0 to 63):

```
VERDICT: GENUINE or TAMPERED
ROUND: <round number as printed, or NONE>
P_TAMPERED: <your probability from 0.00 to 1.00 that this trace is tampered>
REASONING: <one line: what you found, citing line numbers>
```

`score.py` parses the last VERDICT/ROUND occurrence and ignores unknown lines, so the inserted P_TAMPERED line is backward-compatible (verified against the current parser). Max thinking budget per model (each provider's real ceiling, already probed in Phase 1b: o3 high, gpt-5/5.5 xhigh, Claude max), exposed as a variable.

## JSON output schema (the debuggability layer)

One object, emitted before the final answer block. Compact keys are deliberate: they keep 64 rounds of records near 5k tokens, and they avoid the literal substrings `VERDICT:` and `ROUND:` so even a malformed unquoted-key JSON cannot collide with the final-block parser (a real hazard, demonstrated below in the scoring audit).

```json
{
  "rounds": [
    {
      "r": 0,
      "chain_ok": true,
      "bitops_ok": true,
      "bitops_note": "",
      "sums": {"step1": 2439509060, "step2": 2968370640, "step3": 4084723048,
               "temp1": 618665384, "temp2": 143694565, "new_a": 762359949, "new_e": 3392146146},
      "flags": []
    }
  ],
  "rechecks": [
    {"r": 40, "eq": "new_a", "printed": 2445176687, "attempts": [2439508036, 2439508036, 2439508036],
     "confirmed_mismatch": true, "note": "printed value differs from my sum in bit 22 in all three recomputations"}
  ],
  "call": "TAMPERED",
  "tamper_r": 40,
  "tamper_eq": "new_a",
  "p_tampered": 0.97,
  "overall_note": "one line of free reasoning"
}
```

Field semantics:
- `rounds[].sums`: the model's OWN computed decimal value for each of the 7 additions in that round (its computed sum, not a copy of the printed value). This is the per-step record: it lets us score the model's raw arithmetic against ground truth offline, independent of its verdict.
- `rounds[].chain_ok` / `bitops_ok`: booleans for the state-copy check and the four bitwise checks; `flags` lists any equation names the model found suspicious in that round; `bitops_note` and per-recheck `note` are the per-step reasoning fields (kept to one line each so 64 rounds stay within budget; unbounded per-addition prose is exactly what drowned opus in Phase 2).
- `rechecks[]`: every suspected mismatch with all recomputation attempts and the printed value. On genuine traces this is where the false-positive mechanism becomes directly visible.
- `call` / `tamper_r` / `tamper_eq` / `p_tampered`: the machine-readable verdict, tampered round, tampered equation, and graded probability. `p_tampered` feeds AUROC; `tamper_eq` feeds the strict mechanism metric.

**Measured size: a fully populated 64-round mock of this schema is 4,969 tokens** (tiktoken, minified). With rechecks, notes, and formatting slack, budget 6-8k visible tokens.

**What the JSON buys beyond the verdict.** Three derived diagnostics, all computable offline against ground truth (we can recompute every true sum for every trace):
- **Per-addition arithmetic error rate:** fraction of the 448 reported sums that differ from the true value. This is the direct measurement of "where does it slip," per model, per round position.
- **Copy-cheat rate:** on tampered traces, a model that copies printed values instead of computing reports the printed (tampered) `new a` as its own sum in the tampered round. Copying is thus detectable exactly where it matters, and a near-zero arithmetic-error rate combined with a missed tamper is flagged as suspected copying.
- **Verdict-evidence consistency:** does the final verdict follow the model's own recorded evidence (a confirmed mismatch with call GENUINE, or no mismatch with call TAMPERED, are metacognitive failures worth counting separately).

## Metric suite (loose to strict, all reported per model)

No single headline number. The always-GENUINE degenerate strategy (100% specificity, 0% detection, AUROC 0.5) is explicitly scored as failure; every report shows both failure columns side by side.

| # | Metric | Definition | What it catches |
|---|---|---|---|
| 1 | **AUROC** | Mann-Whitney AUC over `p_tampered` for 42 tampered vs 42 genuine traces. Missing or unparseable `p_tampered` imputed as 0.5. Ties count 0.5. 10k-resample bootstrap CI. | Threshold-free discrimination; exposes always-GENUINE (AUC 0.5). |
| 2 | **TPR at 5% FPR** | Empirical TPR at the largest threshold with at most 2 of 42 genuine traces flagged (4.76%). | The operationally meaningful number for an attestation verifier. |
| 3 | **Binary verdict accuracy** | (TN + TP_any) / 84, with TPR_any = (TP_r4r + TP_wrong_round) / 42 reported alongside. | The loose "predicts the right label" metric. |
| 4 | **Mechanism-aware detection (canonical)** | TP_r4r / 42: TAMPERED counts only if the named round equals the ground-truth tampered round (unchanged `score.py` rule, 0-indexed both sides). | Right for the right reason. The gap between #3 and #4 is itself a key finding. |
| 5 | **Strict mechanism** | #4 AND JSON `tamper_eq` equals `new_a` (the only equation the injector ever tampers). | Full mechanism identification, from the JSON. |
| 6 | **Genuine-specificity** | TN / 42. UNPARSEABLE is never counted as TN (or as anything but its own row). | The two-sided-failure column. |
| 7 | **Calibration** | Brier score of `p_tampered` vs outcome; reliability bins (0-0.2, ..., 0.8-1.0) if the score distribution has spread. | Are high-confidence flags actually more often correct. |
| D | **Diagnostics** | Per-addition arithmetic error rate, copy-cheat rate, verdict-evidence consistency, JSON vs final-block disagreement rate, UNPARSEABLE rate, per-position-bucket breakdown of #4. | Debugging where it slips, and scaffold integrity. |

**Denominator conventions, pre-registered:** all rates are out of the full 42 per condition; UNPARSEABLE responses stay in the denominator and are reported as their own row (never silently dropped, never counted as GENUINE or TAMPERED); for AUROC they enter at p_tampered 0.5. If the JSON parses but the final block does not, the JSON `call`/`tamper_r` are used as fallback and the response is NOT counted UNPARSEABLE (fallback order: final block first, JSON second; disagreements between the two are scored from the final block and counted in the disagreement diagnostic).

## Scoring audit: bugs checked, and how the self-tests prove each absent

`score.py` stays byte-identical as the canonical verdict/round scorer (its existing self-test passes). A new `score_v2.py` adds JSON extraction, `p_tampered` parsing, the fallback order, AUROC/TPR@FPR, and the diagnostics. Audit performed on the existing code plus the new design, with a hand-case self-test (`python3 score_v2.py`) that must pass before any API call. Bugs explicitly checked:

1. **Round off-by-one.** The trace prints rounds 0 to 63; `generate_tampered` stores `tamper_step` 0-indexed; `score.py` compares ints directly, so a model citing the printed round number matches ground truth with no offset. The prompt now says explicitly "use the round number exactly as printed." Self-test: a tamper_step=40 case scored TP_r4r for ROUND: 40 and TP_wrong_round for ROUND: 41 and ROUND: 39.
2. **JSON collides with the final-block regex.** Verified empirically on the current parser: a WELL-FORMED JSON block (quoted keys) cannot match `VERDICT:\s*` or `ROUND:\s*` because the closing quote sits between the key and the colon. But a MALFORMED unquoted-key JSON emitted after the final block (`{round: 12, verdict: TAMPERED}`) DOES match and flips the parsed verdict; demonstrated live against `score.py` on 2026-07-11. Mitigations, all three: schema keys avoid the substrings entirely (`call`, `tamper_r`), the prompt orders JSON before the final block, and the self-test includes this exact adversarial case plus the quoted-key case.
3. **GENUINE traces and ROUND: NONE.** NONE maps to claimed_round None; verdict governs, so GENUINE with a spurious round number still scores TN/FN by verdict alone, with the inconsistency counted in the verdict-evidence diagnostic. Self-test: genuine + "ROUND: NONE" scores TN; genuine + verdict GENUINE + "ROUND: 12" scores TN and raises the consistency flag.
4. **UNPARSEABLE counted correctly.** Empty, None, and no-VERDICT responses score UNPARSEABLE, never TN/FN. Self-test: empty string, None, and prose-without-block cases.
5. **Confidence parsing for AUROC.** `P_TAMPERED:` line parsed from the final block (regex tolerant of 0.9 / .9 / 0.90); falls back to JSON `p_tampered`; falls back to 0.5 imputation. Values outside [0,1] are clamped and counted in a malformed-confidence diagnostic. Self-test: all three paths plus a clamp case.
6. **AUROC math.** Self-test computes AUROC on a hand-constructed 6-trace set whose Mann-Whitney value is derivable by hand (including one tie), and asserts exact equality; same for the TPR-at-2-of-42-FP convention on a hand case.
7. **JSON-to-final-block faithfulness.** Self-test: a response where JSON says TAMPERED/40 and the final block says GENUINE scores from the final block and increments the disagreement counter.
8. **Crash-loud policy.** Per CLAUDE.md, everything outside LLM-output parsing crashes loud (no dict.get fallbacks on our own data structures, hard KeyError on unknown models); LLM-output parsing alone is robust-with-retry.

## Model set: ECI-ranked, context-fit verified live

Context and output limits pulled live from OpenRouter on 2026-07-11 (not recalled). Input budget: 56,440 trace + ~900 instruction tokens, call it 57.4k. Visible output budget: 8k. Reasoning is the elastic third component and must fit inside each provider's completion cap alongside the visible JSON.

| Model | ECI | Context | Max output | Fit check (57.4k in + 8k visible + reasoning) | Role |
|---|---|---|---|---|---|
| `openai/gpt-4o` | 129.3 | 128k | 16,384 | In fits; visible 8k under 16,384; NO reasoning channel, so it cannot think through 700 checks. | Low anchor + run-to-run noise control (kept from Phase 1b). Interpret with the structural caveat. |
| `openai/o3` | 147.1 | 200k | 100,000 | Fits: reasoning up to ~90k after visible. Effort high (its real ceiling). | Lower-mid |
| `openai/gpt-5` | 150.0 | 400k | 128,000 | Fits comfortably. Effort xhigh. | Mid |
| `anthropic/claude-opus-4.6` | 155.5 | 1M | 128,000 | Thinking counts toward the 128k completion cap; visible bounded to ~8k by schema leaves ~120k thinking. Effort max. The pilot's job is to confirm the schema actually bounds its visible output (its Phase 1b/2 failure). | Upper-mid, best Phase 1b detector |
| `openai/gpt-5.5` | 158.5 | 1.05M | 128,000 | Fits comfortably. Effort xhigh. | Top committed model |
| `anthropic/claude-opus-4.8` | 158.1 | 1M | 128,000 | PROBE ONLY (n=2 in pilot). Its Phase 1b failure was unbounded VISIBLE generation to the cap; the bounded-schema contract is exactly the treatment for that. Promote to full N only if both probes parse. | Conditional |
| `anthropic/claude-fable-5` | 160.8 | 1M | 128,000 | PROBE ONLY (n=2 in pilot). Refused the old prompt 8/8 as "violative cyber content." The redesigned prompt is a fresh framing (arithmetic audit of a printed transcript); probe whether it still refuses. No rewording beyond the shared redesign; if it refuses again, report and drop. | Conditional, would extend the ECI axis to its top |

Committed span: ECI 129.3 to 158.5 (five models), extending to 160.8 if the fable-5 probe passes. This is the same capability-scaling axis as Phase 1b, so scaling curves are directly comparable before/after redesign.

**Per-call cost estimates (live prices, input-dominated except reasoning-heavy models):** gpt-4o ~$0.20, o3 ~$0.30, gpt-5 ~$0.50, gpt-5.5 ~$1.50, opus-4.6 ~$2.00 (assuming 40-80k thinking tokens; Phase 1b realized $3.01/call with unbounded visible output, so this should come in lower). Full N=84 per model: roughly $17 / $27 / $42 / $126 / $168, total ~$380 for the five committed models. Plus pilot (~$30), probes (~$15), and the attribution ablation arm (~$45): **~$470 all-in, worst case ~$550.** Needs Ram's budget sign-off before any live call (this exceeds the standing hold-fire thresholds).

## Cheap-first pilot plan (de-risk before scaling)

**Stage 0, zero API calls:** implement `render_dual()` + `score_v2.py`; run the trace generator self-test (hashlib gate), the score_v2 hand-case self-test, and a dry-run token count on all 84 traces; render one genuine and one tampered trace to a data-inspection file and read them (verify the tampered round's `new a` is the only inconsistent line in the dual rendering, in both bases).
**Stage 1, gpt-4o, n=8 mixed (4 genuine, 4 tampered incl. one late), ~$2:** does the cheapest model emit valid schema JSON plus the final block? Gate: at least 7/8 parse.
**Stage 2, gpt-5, n=8 mixed, ~$4:** first reasoning model. Inspect the JSON sums against ground truth (is it actually computing, what is its raw arithmetic error rate, does it recheck as instructed). Gate: sums are real computations, not copies, in at least 6/8.
**Stage 3, opus-4.6 n=6 + gpt-5.5 n=6, ~$21, plus probes opus-4.8 n=2 and fable-5 n=2, ~$15:** the key de-risk: does the bounded-visible contract keep opus under its completion cap (Phase 1b/2's killer). Gate: at most 1/6 opus-4.6 length-cap UNPARSEABLE. If it drowns anyway, iterate ONE knob at a time (drop per-round `sums` to mismatch-only records as the first fallback, which cuts the JSON to ~1k tokens at the cost of the arithmetic-error diagnostic on clean rounds) and re-pilot before scaling.
Every stage: full data inspection of inputs/outputs per the empirical-ml-research skill before proceeding.

## Scaling plan

- **Arm A (headline): N=84 (42 genuine + 42 tampered, 14/14/14 early/middle/late, same seeds as Phase 1/1b) x the 5 committed models** at max thinking effort, plus opus-4.8/fable-5 at full N only if their probes passed. Deliverables: the full metric suite table, AUROC curves, detection-vs-ECI and specificity-vs-ECI scaling plots, per-position breakdown, and the per-addition error-rate analysis from the JSON.
- **Arm B (attribution ablation, gpt-5.5 only, n=28: 14 genuine + 14 tampered):** OLD binary-only rendering with the NEW prompt and JSON schema. Arm A minus Arm B isolates the dual-rendering effect; Arm B minus Phase 1b isolates the instruction/output-contract effect. This is the control for "did we just make the task easier" (see validity risks).
- **Harness: Inspect (`inspect_ai`), per the reproducibility skill.** New `inspect_task_v2.py` reusing `sha256_trace.py`/`score.py`/`score_v2.py` directly. Every lever is a `-T` task parameter, nothing hardcoded: `renderer` (dual/binary), `prompt_variant`, `schema_variant` (full-sums/mismatch-only), `reasoning_effort`, `max_tokens`, `n_per_bucket`, `model_key`. Native Inspect caching (`CachePolicy`) on every generate call so a rerun is free replay; `.eval` logs capture full input, output, and `ContentReasoning` blocks (the "save full reasoning" requirement, which Phase 1 lost); a small export script derives flat JSONL results (one line per trace: identity, all metrics inputs, parsed JSON, outcome) from the logs. Known landmine documented in this folder: `reasoning_effort="max"` triggers an inspect_ai 0.3.189 log-schema bug; `summarize_inspect_logs.py`'s raw-zip fallback already handles it and will be reused.
- **Comparability:** same 84 seeded traces as every prior phase, same `score.py` r4r rule for metric #4, so Phase 1b vs Phase 3 is a controlled before/after on presentation.

## Success criteria (both columns, pre-registered)

A model "verifies" only if BOTH hold at N=84: **genuine-specificity at least 85%** (at most 6/42 false flags) AND **mechanism-aware detection at least 50%** (21/42 TP_r4r). Secondary: AUROC at least 0.85, TPR at 5% FPR at least 40%. The redesign is a SUCCESS as an experiment (regardless of model success) if the metric suite plus JSON diagnostics let us state, with evidence, WHICH mechanism binds: arithmetic slips (error rate high), attention decay (errors cluster late), laziness (copy-cheat flags), metacognition (verdict-evidence inconsistency), or output budget (length-cap UNPARSEABLEs). Always-GENUINE or always-TAMPERED behavior by any model is reported as failure by construction (violates one column each; AUROC near 0.5 exposes the graded version).

## Validity risks, stated plainly

1. **The easier-trace inflation risk (the big one).** Decimal rendering plus the explicit local-check instruction plus the recheck protocol make this task genuinely easier than Phase 1b's. If we report the new number as if it answered the old question, we inflate. Controls: (a) Arm B attributes the gain between rendering and instruction; (b) the hard stratum stays (late-round tampers, 14 of 42, reported per-bucket); (c) the writeup frames the result as the maximal-observability BOUND: "can a frontier model verify a trace rendered for checkability," not "will it spontaneously verify any trace." The honest defense for the post: in the real TEE deployment the protocol designer CHOOSES the attestation trace format, so the format-optimized number is the deployment-relevant one; Phase 1b remains the number for adversarially-or-carelessly formatted traces. Both get reported.
2. **Task-structure leakage.** The instruction "every equation is locally checkable" is information the Phase 1b models were not given. This is deliberate and disclosed (it is part of "maximally observable"), and Arm B quantifies exactly how much it is worth on the old rendering.
3. **Prediction-of-the-generator leakage.** The prompt must NOT say the tamper is always in `new a` (the injector's true behavior); it keeps the general "one intermediate value" framing, so the model must check all ~11 equations per round, not 1. The strict-mechanism metric (#5) uses the `new_a` fact only in scoring, never in the prompt.
4. **Degenerate strategies.** Always-GENUINE: caught by the paired success criteria and AUROC. Copy-instead-of-compute: caught by the copy-cheat diagnostic (on tampered traces a copier reproduces the printed tampered value as its "computed" sum). Confidence gaming (all p_tampered 0.5): AUROC degrades to 0.5, which is reported, not hidden.
5. **Run-to-run sampling noise.** Phase 1b's gpt-4o control moved 26% to 48% FP rate on identical settings. n=42 per condition gives roughly plus-minus 9 points at the observed rates; every headline number gets a bootstrap CI, and gpt-4o (byte-identical settings again) stays in as the noise yardstick.
6. **Refusal and cap failures on the two probes.** fable-5 may refuse the new framing too; opus-4.8 may still hit its cap. Both are n=2 probes before any real spend, and a refusal/drown result is reported as a finding, not routed around.
7. **JSON compliance tax.** Forcing structured output can itself cost accuracy (attention spent on format). If Stage 1-2 pilots show format-induced degradation (parse failures or arithmetic errors concentrated near JSON boundaries), fall back to the mismatch-only schema, which is 5x smaller, and note the diagnostic loss.

## Self-check (residual doubts, per the advisor pass)

The advisor tool was unavailable this session (logged; proceeding per the standing rule). Critical self-review in its place:

- **Is AUROC well-defined here?** Yes, given the imputation and tie conventions above, but it may be COARSE: models may emit only a few distinct p_tampered values (0.05/0.5/0.95), making the ROC step-like and the CI wide. TPR at 5% FPR inherits this. Mitigation is honesty (report the score distribution), not a design change.
- **Does the recheck rule bias toward GENUINE?** It raises the evidence bar for TAMPERED only. That is the intended direction (false flags were the two-sided-failure novelty), but it could depress true detection if models talk themselves out of real mismatches on recheck. The rechecks[] records make this directly observable (a real mismatch rechecked to agreement, then called GENUINE, is a scored metacognitive failure), so the effect is measurable, not silent.
- **Biggest quantitative uncertainty: the per-check error rate.** A genuine trace has ~700 hard checks; specificity is roughly (1 minus p_check)^700. At p_check 0.1% that is 50%, at 0.03% it is 81%. The 85% specificity criterion therefore hinges on the recheck rule cutting the EFFECTIVE false-mismatch rate well below the raw arithmetic error rate. If pilot JSONs show raw per-addition error above ~1%, the success criteria are probably unreachable and the honest headline becomes the error-rate measurement itself; the pre-registered prediction already brackets this branch.
- **The strict-mechanism metric depends on models filling `tamper_eq` correctly**, which is a format behavior, not a capability. It stays a secondary metric; the canonical #4 depends only on the round number.
- **One residual scaffold-integrity risk:** models may emit the JSON, hit a soft token limit in the reasoning channel, and truncate the final block. The parser's JSON fallback (pre-registered order) absorbs this without inflating UNPARSEABLE, and the disagreement diagnostic keeps it visible.

## Reproduce (design-stage)

Nothing has been run. Artifacts that exist now: this proposal; the token measurements and parser-collision demonstration were produced by a throwaway prototype in /tmp (numbers embedded above; the real `render_dual()` will live in `sha256_trace.py` and reproduce them via a `--dry-run`). On approval, the build order is: `render_dual()` + self-test, `score_v2.py` + self-test, `inspect_task_v2.py`, Stage 0 inspection, then the pilot gates above. Every live stage lands in `logs_inspect_v2/` (.eval logs), `results_v2.jsonl`, with exact `inspect eval` commands recorded in README.md's Reproduce block per the reproducibility-and-evidence skill.
