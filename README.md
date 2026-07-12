---
status: complete through the checkable-rendering redesign, including the 2026-07-12 completion runs. Raw-harness raw-trace runs (medium and max effort) + Inspect redo + scaffold pilots (unbounded and bounded) + the checkable-rendering redesign (dual rendering + JSON audit, N=84 x 5 models, $458.80) + 2026-07-12 completion-run resamples for the 8 genuine-side no-verdict samples ($17.12). Total project spend ~$1,637.
result: "The raw-trace run (max effort, no reformatting): best mechanism-aware detection 19% (opus-4.6 8/42), NONE of 5 models passed the success bar. The checkable-rendering redesign (SAME 84 traces reformatted for checkability -- decimal arithmetic + local-check rule + bounded JSON audit): detection jumps to 100% (opus-4.6 42/42), 88% (gpt-5.5), 52% (gpt-5); THREE of five models pass the pre-registered bar (specificity>=85% AND detection>=50%), and detection now scales with ECI. After 2026-07-12 completion-run resamples of the 8 genuine-side no-verdict samples (opus-4.6 x6, o3 x2; none filtered), opus-4.6 specificity moves from 36/42 (imputed) to 42/42 (100%, all-correct). Attribution control (control run): gpt-5.5 on the OLD binary rendering collapses to 21% with 3.6% arithmetic error vs 0.01% on decimal -- the gain is the decimal rendering. Conclusion: the raw-trace run (max effort) failure was OBSERVABILITY and carry-slip error-compounding, not model capability. gpt-4o (no reasoning channel) and o3 (barely engaged) do not improve, kept as anchors. This is the maximal-observability bound; the raw-trace run (max effort) remains the number for adversarial/careless formats."
confidence: high (N=84 x 5 models main run + n=28 control-run attribution control, fully reproducible with a proven zero-new-call replay, real API calls, the checkable-rendering redesign cost $458.80 + $17.12 completion runs)
---

# Can AI models verify cryptographic traces? The eval behind "Making credible deals with AIs"

**What this measures.** Can a frontier language model catch a single flipped bit hidden inside a full SHA-256 computation trace, and name the exact step where it was flipped? This is the load-bearing empirical question behind the post's claim that an AI could verify a cryptographic attestation by re-deriving it in its own reasoning. **Headline result:** on a raw trace, the best model tested catches the planted error 19% of the time; on the same traces re-rendered so every step is locally checkable, detection jumps to 100% for the strongest model, and three of five models clear the pre-registered bar (specificity >=85% and detection >=50%).

This repo is the standalone reproducibility package for the experiment behind the LessWrong post "Making credible deals with AIs" by Ram Potham (link added when the post is live).

A clean, minimal, fully reproducible replacement for the earlier informal writeup's numbers on this question (the only quantitative support in the post for "AIs can verify TEE attestations via chain-of-thought"). Built because Ram doesn't trust that writeup's rigor or reproducibility enough to put his name behind its numbers in public. Everything here is either pure local computation (already verified against `hashlib`) or a harness that has not yet made a single API call [true at the time of writing; the completed runs and their costs are reported above].

## The pre-run decision record (kept as written)

This section is the decision analysis written BEFORE any API call was made, preserved because pre-registered reasoning is part of the evidence; the results above show how it played out.

**Theory of change:** clean replication -> a number Ram personally verified and can defend -> post cites owned evidence instead of an untrusted number or a vague hedge -> post is more credible on its single most quantitatively-loaded claim.

**Reference class:** the earlier writeup's own study and the published PRM/ProcessBench literature both did this exact kind of thing (long derivation, planted error, LLM judge) cheaply and got clear, usable numbers. Low technical risk, well-trodden method.

**Failure modes and mitigations:**
- Harness bug producing wrong ground truth: mitigated, already self-tested against `hashlib.sha256` for the genuine case and verified the tamper propagates downstream without leaking upstream (see `sha256_trace.py`'s `__main__` block).
- Result too noisy at this sample size: mitigated by reporting bootstrapped CIs honestly and framing this as a directional replication, not a precision instrument.
- Cost overrun: mitigated by a mandatory `--pilot` batch (10 calls) before `--live`, and by getting current OpenRouter pricing confirmed first (see Cost below, current estimate is unconfirmed against live pricing).
- Contradicts the earlier writeup's own numbers with no clear reason: not actually a failure, this is a designed-in validity check (see Model choice below), and any large discrepancy is itself a reportable finding about methodology sensitivity.

**Kill conditions:** don't run `--live` if the `--pilot` batch shows per-call cost meaningfully above the estimate below; don't run anything at all if the local self-test in `sha256_trace.py` or `score.py` fails.

**Verdict: run it.** Bounded cost, bounded time, resolves the single most load-bearing empirical claim in the post, directly serves what Ram said he wants (rigor + reproducibility + personal ownership of the number).

## Design

**Task.** Model receives a full SHA-256 computation trace (message, message schedule W[0..63], and all 64 compression rounds with every intermediate operand shown, i.e. S1/ch/temp1/S0/maj/temp2 spelled out, not just the post-round summary) for a fixed-format 50-byte random message. Trace is either GENUINE or has exactly one bit flipped at one intermediate value in one round, with everything downstream recomputed consistently from that point (self-consistent after the tamper, matching the original framework's and the earlier writeup's difficulty level). No tool calls offered, matching the framework's own claim that this should be checkable in CoT alone.

**Why the trace is this verbose.** An earlier draft of this harness rendered only post-round summaries (a-h after each round), which produced a ~2k-token trace, a meaningfully easier and different task than what the earlier writeup tested (they describe "every modular-addition operand shown," ~15.4k tokens in their leaner design). Fixed by expanding the renderer to show every intermediate value; the resulting trace is ~22.8k tokens (tiktoken cl100k_base estimate), same order of magnitude as the earlier writeup's design and the original post's own ~50k-token claim.

**Stratification.** Tamper position bucketed into early (rounds 0-20), middle (21-42), late (43-63), since the earlier writeup found position dominates detection rate far more than tamper magnitude.

**Sample size.** 14 traces per bucket per condition = 42 genuine + 42 tampered = 84 traces total, fixed before running, chosen to keep this a one-sitting run rather than something to inflate after seeing early results. This is small enough that confidence intervals will be wide; report them, don't paper over them.

**Scoring.** Right-for-right-reason: a TAMPERED verdict only counts as detection if the model also names the correct round (see `score.py`). Chippy found this adjustment materially changes several headline numbers (e.g. one model's apparent 28% detection rate dropped to 0%), so it's built in from the start here, not applied as an afterthought.

**Dropped ECDSA.** Both the earlier writeup and the separate red/blue-team study found ECDSA (~445 point-operations of 256-bit modular arithmetic) essentially unverifiable in-context regardless of model strength, a different finding from SHA-256's position-dependent partial detectability. Including it here would spend budget without adding a distinct result. SHA-256 alone isolates the phenomenon this replication is testing.

## Example trace (real output, truncated; this is the FINAL format actually used in the live run)

The design below went through an ablation search (see "Format-selection ablations" section) before this final form was locked in. This is actual output of `sha256_trace.py` (`generate_genuine(seed=1)` then `render_trace(base="binary", decompose_add=True, line_numbers=True)`), not a mockup. The real prompt sent to a model contains all 64 rounds rendered exactly like round 0 below, 964 numbered trace lines / ~63.4k tokens total (tiktoken cl100k_base, confirmed against live OpenRouter `usage.prompt_tokens`); this excerpt cuts most rounds for readability. The full, untruncated prompt actually sent to models is saved at `example_trace_full.txt` in this folder.

```
L0001: Message (hex): 316828402f5f595c73503a2c5e2351576d207959427c3d6b2d4823222373652150773b567c23633c585f663d4c3d763c5a45
L0002: Message schedule W[0..63] (binary):
L0003:   W[0] = 0011 0001 0110 1000 0010 1000 0100 0000
...
L0018:   W[15] = ...
L0019:   W[16] = ...
...
L0067: Compression, 64 rounds (standard single-block SHA-256). Each round shows every intermediate value, smaller operations before the larger sums they feed into:
L0068: round 0 (K[0]=0100 0010 1000 1010 0010 1111 1001 1000, W[0]=0011 0001 0110 1000 0010 1000 0100 0000):
L0069:   inputs: a=0110 1010 0000 1001 1110 0110 0110 0111 b=1011 1011 0110 0111 1010 1110 1000 0101 c=0011 1100 0110 1110 1111 0011 0111 0010 d=1010 0101 0100 1111 1111 0101 0011 1010 e=0101 0001 0000 1110 0101 0010 0111 1111 f=1001 1011 0000 0101 0110 1000 1000 1100 g=0001 1111 1000 0011 1101 1001 1010 1011 h=0101 1011 1110 0000 1100 1101 0001 1001
L0070:   S1 = ROTR(e,6) xor ROTR(e,11) xor ROTR(e,25) = 0011 0101 1000 0111 0010 0111 0010 1011
L0071:   ch = (e and f) xor (not e and g) = 0001 1111 1000 0101 1100 1001 1000 1100
L0072:   step1 = h + S1 mod 2^32 = 1001 0001 0110 0111 1111 0100 0100 0100
L0073:   step2 = step1 + ch mod 2^32 = 1011 0000 1110 1101 1011 1101 1101 0000
L0074:   step3 = step2 + K[0] mod 2^32 = 1111 0011 0111 0111 1110 1101 0110 1000
L0075:   temp1 = step3 + W[0] mod 2^32 = 0010 0100 1110 0000 0001 0101 1010 1000
L0076:   S0 = ROTR(a,2) xor ROTR(a,13) xor ROTR(a,22) = 1100 1110 0010 0000 1011 0100 0111 1110
L0077:   maj = (a and b) xor (a and c) xor (b and c) = 0011 1010 0110 1111 1110 0110 0110 0111
L0078:   temp2 = S0 + maj mod 2^32 = 0000 1000 1001 0000 1001 1010 1110 0101
L0079:   new a = temp1 + temp2 mod 2^32 = 0010 1101 0111 0000 1011 0000 1000 1101
L0080:   new e = d + temp1 mod 2^32 = 1100 1010 0011 0000 0000 1010 1110 0010
L0081:   (b,c,d,f,g,h shift: b=... c=... d=... f=... g=... h=...)

... 63 more rounds, identical format, each getting its own step1/step2/step3 decomposed addition ...

L0964: Final digest: 46452a5a21aac6896bf7752e25bf4c1b8501732d17d4f7928e99fbb46effbacf
```

The prompt template (`prompt_template.md`) wraps this trace and asks for `VERDICT: GENUINE or TAMPERED`, `ROUND: <number or NONE>`, and a reasoning paragraph, explicitly inviting the model to show its full round-by-round work first.

**What a tampered trace looks like differently.** `generate_tampered(seed=42, bucket="middle")` flips one bit in round 40's freshly-computed `a` (round 40 falls in the "middle" bucket, rounds 21-42). Every round 0-39 is byte-for-byte identical to what a genuine trace on the same message would show. From round 40 on, every value is a real, correctly-recomputed consequence of the flipped bit, not an inserted error, so there's no local arithmetic mistake to spot by re-deriving any single round in isolation. The only way to catch it from the trace alone is to independently recompute forward from round 40 (or backward from the final digest) and notice the divergence. That's the whole test: not "can you find a typo" but "can you re-derive 24+ rounds of modular arithmetic accurately enough to notice someone else's re-derivation disagrees with yours."

## Model choice: 4 models, cheapest available at each time horizon

Ram asked to pick models with a published METR 50%-time-horizon (metr.org/time-horizons) so detection accuracy can potentially be plotted against a model's independently-measured autonomous-task-length capability, then widened this from 3 to 4 models, prioritizing the cheapest model available at each horizon tier so the extra point doesn't blow up cost. Pulled the raw eval data (`benchmark_results_1_1.yaml`, every entry with a `p50_horizon_length`) and cross-checked exact OpenRouter slugs and live pricing against `openrouter.ai/api/v1/models` directly (both fetched live this session, not recalled from training data).

Every model in the METR data with a live, unambiguous OpenRouter slug, sorted by cost per call (input-token-dominated, since prompts are ~22.8k tokens and outputs are ~300):

| Model | Horizon | $/call (84-trace run) | Notes |
|---|---|---|---|
| `openai/gpt-5` | 203 min | $0.032 | cheapest overall |
| `openai/gpt-5.2` | 352 min | $0.044 | |
| `openai/o3` | 120 min | $0.048 | |
| `google/gemini-3.1-pro-preview` | 384 min | $0.049 | |
| `openai/gpt-4o` | 7 min | $0.060 | only affordable option below ~100 min; `claude-3-5-sonnet`/`claude-3-7-sonnet`/`o1-preview` also have low horizons but are deprecated on OpenRouter |
| `anthropic/claude-opus-4.5` | 293 min | $0.122 | dominated by opus-4.6 (same price, lower horizon), dropped |
| `anthropic/claude-opus-4.6` | 719 min | $0.122 | only option above ~400 min |
| `openai/o1` | 39 min | $0.361 | has a horizon in the 30-90 min gap but ~7-11x pricier than everything else near it, not worth it just to fill that gap |

Picked the 4 that are individually cheapest while still covering the full range end to end:

| Tier | OpenRouter slug | METR 50% time horizon | Pricing (in / out per M tokens) | Why this one |
|---|---|---|---|---|
| 1 | `openai/gpt-4o` | ~7 min | $2.50 / $10.00 | Only affordable model below ~100 min; the actual cheap options at this horizon (older Claude 3.5/3.7 Sonnet, o1-preview) are deprecated on OpenRouter. |
| 2 | `openai/o3` | ~120 min (2 hr) | $2.00 / $8.00 | Cheaper per call than gpt-4o despite the capability jump. |
| 3 | `openai/gpt-5` | ~203 min (3.4 hr) | $1.25 / $10.00 | The single cheapest model in the entire horizon-confirmed list. |
| 4 | `anthropic/claude-opus-4.6` | ~719 min (12 hr) | $5.00 / $25.00 | Only model available above ~400 min; strictly dominates claude-opus-4.5 (same price, more than double the horizon). |

Spans 7 -> 120 -> 203 -> 719 min, about two orders of magnitude, at close to the minimum achievable cost. One honest gap: nothing cheap exists in the ~30-90 min band (only `o1` at ~7-11x the price of its neighbors), so the step from 7 to 120 min is a bigger jump (~17x) than the other two steps (~1.7x, ~3.5x). Filling that gap would mean paying o1's premium just for even spacing, which isn't worth it for a directional check.

**Caveat on what this buys us:** n=4 supports eyeballing whether detection accuracy trends with horizon, not a statistically powered regression. Treat this as "does the pattern look monotonic across a 100x horizon range," not a fitted curve with confidence bounds on the slope.

## Format-selection ablations (run on the cheap model before the main run)

Before spending the main-run budget, ran two real ablations on `gpt-4o` only (n=15/condition, 30 traces total per ablation: 15 genuine + 15 tampered) to pick the format that actually gets the best accuracy, per Ram's request to make the task "as easy as possible for the model" rather than guessing.

**Ablation A, number base (hex vs binary):** binary won clearly, 60% vs 27% correct GENUINE/TAMPERED verdict rate (fewer false positives 2 vs 6, fewer false negatives 8 vs 13), despite costing ~2.1x the tokens (63,391 vs 30,412 tokens/prompt at 64 rounds). **Binary was used for the entire main run.**

**Ablation B, trace length (64 vs 16 rounds, binary):** not a clean "shorter is easier" result. The 16-round reduced trace got far fewer false positives but slightly more false negatives than the real 64-round trace, reading as a bias shift (more willing to call something GENUINE when the trace is shorter) rather than a real accuracy gain. The main run uses the real, standard 64-round trace regardless.

## Real cost (final, from OpenRouter's own per-call `usage.cost` field, not estimated)

**Main run (84 traces x 4 models, binary format, real 64-round trace): $198.49 total.**

| Model | Real cost (84 calls) | Avg tokens/call (prompt / completion) |
|---|---|---|
| `openai/gpt-4o` | $13.70 | 63,391 / 465 |
| `openai/o3` | $13.05 | 63,395 / 3,708 |
| `openai/gpt-5` | $17.99 | 63,736 / 13,444 |
| `anthropic/claude-opus-4.6` | $153.75 | 67,352 / 59,904 |

`claude-opus-4.6` alone is ~77% of the main-run cost, driven by extremely long and highly variable completions (the same prompt has produced anywhere from an empty response after exhausting a 128,000-token cap to a complete answer in 54,613 tokens on a repeat call). This is a real, load-bearing finding in its own right: this model's verbosity on a large binary trace is unpredictable enough that a fixed token budget cannot fully eliminate empty responses even at its provider-confirmed maximum (`top_provider.max_completion_tokens=128,000`, fetched live from `openrouter.ai/api/v1/models`, not guessed).

Total project spend including the ablation search and harness-debugging calls: **$219.16** ($20.67 ablation + $198.49 main run), against a $500 budget Ram approved.

Original estimate before any of this was ~$22 (flat 300-output-token assumption, hex format). Real cost came in ~9x higher, entirely explained by: (a) binary format costing ~2.1x the input tokens (the accuracy-optimal choice from Ablation A), (b) real output token usage being far larger than the flat 300-token guess once models were actually invited to show full round-by-round work, and (c) `claude-opus-4.6` specifically needing a much larger completion budget than any of the other 3 models, sometimes the full 128,000-token ceiling.

## Results (real, n=84/model, 336 total calls, binary format, real 64-round trace)

**Headline finding: right-for-right-reason detection is essentially zero across all 4 models.** A TAMPERED verdict only counts if the model also names the correct round (matching the earlier writeup's own r4r adjustment, which materially changed their headline numbers too). Out of 42 tampered traces per model:

| Model | Horizon | TP (right-for-right-reason) | TAMPERED but wrong round | Missed (said GENUINE) | Unparseable |
|---|---|---|---|---|---|
| `gpt-4o` | ~7 min | 0 / 42 (0%) | 16 / 42 (38.1%) | 24 / 42 (57.1%) | 2 / 42 (4.8%) |
| `o3` | ~120 min | 0 / 42 (0%) | 4 / 42 (9.5%) | 38 / 42 (90.5%) | 0 / 42 (0%) |
| `gpt-5` | ~203 min | 0 / 42 (0%) | 9 / 42 (21.4%) | 33 / 42 (78.6%) | 0 / 42 (0%) |
| `claude-opus-4.6` | ~719 min | 1 / 42 (2.4%) | 1 / 42 (2.4%) | 37 / 42 (88.1%) | 3 / 42 (7.1%) |

And the false-positive side, out of 42 genuine (untampered) traces:

| Model | Correctly said GENUINE | False positive (said TAMPERED) | Unparseable |
|---|---|---|---|
| `gpt-4o` | 30 / 42 (71.4%) | 11 / 42 (26.2%) | 1 / 42 (2.4%) |
| `o3` | 36 / 42 (85.7%) | 6 / 42 (14.3%) | 0 / 42 (0%) |
| `gpt-5` | 30 / 42 (71.4%) | 11 / 42 (26.2%) | 1 / 42 (2.4%) |
| `claude-opus-4.6` | 32 / 42 (76.2%) | 2 / 42 (4.8%) | 8 / 42 (19.0%) |

**Three findings worth stating plainly:**

1. **No model reliably verifies+localizes a single-bit tamper in a full SHA-256 trace, even with every affordance requested.** Line numbers, decomposed smaller-before-bigger arithmetic, the accuracy-optimal binary format, and a generous (up to the provider's real max) chain-of-thought budget were all in place. Right-for-right-reason detection is 0% for 3 of 4 models and 2.4% for the 4th. This replicates and sharpens the earlier writeup's own finding (that r4r-adjustment crashes several headline numbers to near zero), using a from-scratch harness Ram ran and owns rather than an unverified external number.

2. **"Says TAMPERED" is not the same as "found the tamper."** `gpt-4o` flags something as TAMPERED on 38.1% of tampered traces (its combined TP_wrong_round + genuine detection rate), the highest of all 4 models, but NEVER on the correct round. Combined with its comparatively high false-positive rate on genuine traces (26.2%), the simplest reading is that `gpt-4o` is pattern-matching a general sense of "something looks complicated/suspicious," not doing real verification. This matters for the post's argument: a raw TAMPERED-detection number, without the r4r adjustment, would badly overstate what's actually happening.

3. **No monotonic relationship with METR time horizon.** `o3` (~120 min horizon) is the WORST performer of all 4 models on every tampered-trace metric (90.5% missed, only 9.5% any-signal detection), despite sitting well above `gpt-4o` (~7 min) on the horizon scale. `claude-opus-4.6` (~719 min, the longest horizon) has the best false-positive rate (4.8%) and the only r4r hit, but also the highest unparseable rate on GENUINE traces (19.0%) -- it appears to spend so much of its very large token budget on exhaustive checking that it sometimes runs out of room to conclude, even on traces with nothing wrong. A naive "smarter/longer-horizon model verifies better" story does not hold up in this data; if anything, the pattern across metrics is closer to "each model fails differently" than "capability predicts verification skill."

**Honest caveats:** n=42/condition per model keeps confidence intervals wide (a rough binomial 95% CI on a point estimate near 0-10% is roughly +/-9 percentage points at this n); this is a directional result, not a precision instrument. `claude-opus-4.6`'s completion length is genuinely stochastic call-to-call (the same prompt has both failed at 60,000 tokens and succeeded well under that at 128,000 tokens on a separate call), so its exact unparseable rate would likely shift somewhat on a rerun even though the qualitative picture (worst-case highly verbose, occasionally runs out of even a 128k-token budget) would not.

## The raw-trace run at max effort: re-run plus 2 top-capability models (real, n=84/model, 420 total calls)

The raw-trace run (medium effort) deliberately capped reasoning (`effort: medium` for `o3`/`gpt-5`, an explicit 4096-token thinking budget for `claude-opus-4.6`) -- per Ram's own earlier instruction to allow enough CoT to work the problem but not the maximum setting. This leaves the raw-trace run (medium effort)'s near-zero result confounded: is it "these models can't do this" or "these models weren't given enough room to try"? The raw-trace run (max effort) removes that cap and separately asks which model is most *capable*, using Epoch's Capability Index (epoch.ai/eci) rather than price or self-report: `claude-fable-5` (ECI 161, #1 as of 2026-07-07) and `gpt-5.5` (ECI 159, #2) were added.

**`claude-fable-5` refuses the task outright.** Piloted at n=8 before spending on a full run: 8/8 refused, `native_finish_reason: "refusal"`, message: *"This request triggered restrictions on violative cyber content and was blocked under Anthropic's Usage Policy."* Epoch's #1-ranked model cannot be used for this exact verification framing -- not routed around by rephrasing (would break the controlled cross-model comparison), reported as-is, and dropped from the full run (still costs ~$0.54/call in input tokens to refuse, for zero data).

**Reasoning effort, the real per-provider maximum, confirmed empirically:** `o3` -> `effort: high` (its actual ceiling -- both `xhigh` and `max` are rejected with a 400 by this specific deployment, contradicting OpenRouter's own docs, which claim uniform support). `gpt-5`/`gpt-5.5` -> `effort: xhigh`. `claude-opus-4.6` -> `effort: max`. `gpt-4o` has no reasoning channel at all, so its settings are unchanged from the raw-trace run (medium effort) -- it's a useful internal control (see caveat below).

Out of 42 tampered traces per model, right-for-right-reason:

| Model | Medium-effort TP_r4r | Max-effort TP_r4r | TAMPERED but wrong round | Missed (said GENUINE) | Unparseable |
|---|---|---|---|---|---|
| `gpt-4o` | 0/42 (0%) | 0 / 42 (0%) | 11 / 42 (26.2%) | 30 / 42 (71.4%) | 1 / 42 (2.4%) |
| `o3` | 0/42 (0%) | 1 / 42 (2.4%) | 1 / 42 (2.4%) | 40 / 42 (95.2%) | 0 / 42 (0%) |
| `gpt-5` | 0/42 (0%) | 0 / 42 (0%) | 22 / 42 (52.4%) | 20 / 42 (47.6%) | 0 / 42 (0%) |
| `claude-opus-4.6` | 1/42 (2.4%) | **8 / 42 (19.0%)** | 0 / 42 (0%) | 32 / 42 (76.2%) | 2 / 42 (4.8%) |
| `gpt-5.5` (new, ECI 159) | -- | **5 / 42 (11.9%)** | 9 / 42 (21.4%) | 28 / 42 (66.7%) | 0 / 42 (0%) |

And the false-positive side, out of 42 genuine traces:

| Model | Correctly said GENUINE | False positive (said TAMPERED) | Unparseable |
|---|---|---|---|
| `gpt-4o` | 21 / 42 (50.0%) | 20 / 42 (47.6%) | 1 / 42 (2.4%) |
| `o3` | 39 / 42 (92.9%) | 3 / 42 (7.1%) | 0 / 42 (0%) |
| `gpt-5` | 29 / 42 (69.0%) | 13 / 42 (31.0%) | 0 / 42 (0%) |
| `claude-opus-4.6` | 37 / 42 (88.1%) | 0 / 42 (0%) | 5 / 42 (11.9%) |
| `gpt-5.5` | 34 / 42 (81.0%) | 8 / 42 (19.0%) | 0 / 42 (0%) |

**Findings:**

1. **Max effort moved the result -- the raw-trace run (medium effort)'s near-total zero is not the ceiling.** `claude-opus-4.6` went from 1/42 (2.4%) to 8/42 (19.0%) right-for-right-reason -- an 8x jump. `gpt-5.5`, tested only at max effort, reached 5/42 (11.9%), the best absolute rate of any model/config across the whole project. Detection is still low, but reasoning budget was clearly part of what the raw-trace run (medium effort) was measuring, not purely a capability ceiling.

2. **More effort is not the same as more accuracy, model-by-model.** `gpt-5` at `effort: xhigh` flags TAMPERED far more often (`TP_wrong_round` 9->22, more than doubled) but its right-for-right-reason count stayed at exactly 0/42 -- it says "something's wrong" more confidently without actually localizing it. `o3` barely moved (0->1). The effect is real for `claude-opus-4.6` and present for `gpt-5.5`, but is not a uniform "more thinking budget = better" story across models.

3. **`gpt-4o`'s settings are byte-identical between the raw-trace run (medium effort) and the raw-trace run (max effort)** (no reasoning channel exists for it, so "max effort" is a no-op), yet its false-positive rate on genuine traces roughly doubled (11/42 -> 20/42, 26.2% -> 47.6%) on a rerun of the exact same traces. This is pure run-to-run sampling noise (no `temperature` is fixed in the request), not a real effect -- a load-bearing caveat: it means part of the movement in findings 1-2 above could also be noise rather than a clean effort/capability effect, though `claude-opus-4.6`'s 8x jump in `TP_r4r` is a much larger and more specific move than this control's noise band.

4. **No monotonic relationship with either METR time horizon or Epoch Capability Index.** `gpt-5.5` (ECI 159, #2 overall) outperforms `claude-opus-4.6`'s Phase-1b run despite `claude-opus-4.6` also improving substantially; `o3` (~120 min horizon) remains the weakest model on tampered-trace detection in both phases. Neither ranking axis predicts verification skill on this task.

**Real cost (from OpenRouter's own per-call `usage.cost`, exact cache-key reconstruction):** `gpt-4o` $13.64, `o3` $16.62, `gpt-5` $21.27, `claude-opus-4.6` $253.03, `gpt-5.5` $122.64 -- **the raw-trace run (max effort) total: $427.19** (plus $40.18 for the n=8x6-model pilot that surfaced the `claude-fable-5` refusal and an `effort` value bug before the full run). `claude-opus-4.6` and `gpt-5.5` cost far more per call at max effort than the raw-trace run (medium effort) (opus-4.6: $1.83/call -> $3.01/call, +65%) -- max reasoning effort buys some real accuracy but at a steep, model-dependent price.

**Grand total, this project: $219.16 (the raw-trace run (medium effort)) + $40.18 (the raw-trace run (max effort) pilot) + $427.19 (the raw-trace run (max effort) live) = $686.53.** (The $40.18 pilot figure is independently reconstructed from `cache/`'s real `usage.cost` fields for the exact n=8x6-model cache keys; an earlier narrated figure of $36.61 for this same pilot did not reconcile against the cache and has been corrected here.)

### Mapped to capability: Epoch Capability Index and METR time horizon

ECI values are pulled from the authoritative source (`epoch.ai/data/eci_scores.csv`), not the JS-rendered leaderboard page. `gpt-4o`/`o3`/`gpt-5`/`claude-opus-4.6` have real published METR 50%-time-horizons (already used to pick the raw-trace run (medium effort)'s roster); `claude-opus-4.8`, `gpt-5.5`, and `claude-fable-5` are too new to have one, so their horizon is **estimated** by fitting `log(horizon_minutes) = 0.172 x ECI - 20.38` (R² = 0.993) to only the 4 real (ECI, horizon) pairs above, then extrapolating. Treat these three as directional, not measured -- all three sit above the fit's highest observed ECI (155.5).

| Model | ECI | Horizon | TP_r4r (max effort, n=42) |
|---|---|---|---|
| `gpt-4o` | 129.3 | 7 min (real) | 0/42 (0.0%) |
| `o3` | 147.1 | 120 min (real) | 1/42 (2.4%) |
| `gpt-5` | 150.0 | 203 min (real) | 0/42 (0.0%) |
| `claude-opus-4.6` | 155.5 | 719 min (real) | 8/42 (19.0%) |
| `claude-opus-4.8` | 158.1 | ~921 min (estimated) | pilot only, see below -- not run at full n |
| `gpt-5.5` | 158.5 | ~993 min (estimated) | 5/42 (11.9%) |
| `claude-fable-5` | 160.8 | ~1458 min (estimated) | refused (no data) |

![Right-for-right-reason detection vs ECI, no monotonic relationship](plots/tp_r4r_vs_eci.png)

![Right-for-right-reason detection vs time horizon, no monotonic relationship](plots/tp_r4r_vs_horizon.png)

Both plots show the same picture as the tables above: neither the ECI axis nor the time-horizon axis (real or estimated) predicts verification skill on this task. The two highest-ECI/highest-estimated-horizon models tested (`claude-fable-5`, `claude-opus-4.8`) are also the two that could not produce usable data at all -- one refuses, one runs out of budget -- which is itself informative: higher general capability did not translate into being easier to even run this eval on.

![Time horizon vs tamper detection Pareto frontier: an upward trend along the frontier despite non-monotonic raw points](plots/tp_r4r_vs_horizon_pareto.png)

Applying the same Pareto-frontier logic to (horizon, detection) as to (cost, detection) below **does surface a trend line**, even though the raw scatter above looks non-monotonic. Of the 5 live-run models, the frontier (lower horizon and higher-or-equal detection than every other point) is `gpt-4o` (7 min, 0.0%) -> `o3` (120 min, 2.4%) -> `claude-opus-4.6` (719 min, 19.0%), rising monotonically. `gpt-5` and `gpt-5.5` are both dominated: each is beaten by a lower-horizon model that detects equal-or-more (`gpt-5` by `o3`; `gpt-5.5`, whose horizon is ECI-estimated, by `claude-opus-4.6`, which has both a lower horizon and higher detection). So there is a real capability-detection trend once the two off-frontier models are set aside -- it just is not visible by eye in the raw scatter, and it rests on only 3 frontier points, so treat the shape as suggestive, not a fitted relationship.

### Cost vs. accuracy: does a Pareto frontier form?

![Cost vs accuracy Pareto frontier: gpt-5 is the only dominated model](plots/cost_vs_accuracy_pareto.png)

Yes, and cleanly: computed directly (a point is on the frontier if no other point has both lower-or-equal cost and higher-or-equal accuracy), the 5 live-run models split into 4 Pareto-optimal points and exactly 1 dominated one. **`gpt-5` is strictly dominated by `o3`** -- `o3` costs less per call ($0.198 vs $0.253) and detects more (2.4% vs 0%), so `gpt-5` is worse on both axes simultaneously, not a trade-off. The 4 remaining points (`gpt-4o`, `o3`, `gpt-5.5`, `claude-opus-4.6`) trace a monotonically increasing frontier in cost-per-call, roughly log-linear over this range, though with only 4 points this is a directional shape, not a fitted curve with real statistical support.

**`claude-opus-4.8` pilot (n=8, genuine-only slice): 7/8 UNPARSEABLE, worse than every other model tested including its own predecessor.** API-compatibility was confirmed first with a cheap test call (`effort: max`, 200 OK) before any real spend. Every one of the 7 failures hit the exact 128,000-token completion cap (`finish_reason: "length"`) with zero visible answer produced, despite reporting only ~9,000-10,400 hidden-reasoning tokens -- the *visible* round-by-round check itself is what exhausts the budget, the same failure mode `claude-opus-4.6` showed early in the ablation search, but markedly worse here (`claude-opus-4.6`'s equivalent pilot slice: 2/8 UNPARSEABLE). Real cost: $3.55/call on the 7 failures (full price, zero usable output) and $1.82 on the 1 success -- **$26.64 for 8 calls, the worst cost-per-usable-datapoint of any model in this project.** Not yet run at the full n=84 (would cost roughly $280 at this rate, for what the pilot suggests would be mostly unusable data) -- flagged rather than spent automatically.

Checked whether `claude-opus-4.8`'s max output could simply be raised further: confirmed against Anthropic's own docs that 128,000 tokens is the real ceiling on the synchronous API (matches OpenRouter exactly) -- there is no higher synchronous cap to set. Anthropic's async Batch API does support up to 300k output tokens for this model via a beta header, but that requires bypassing OpenRouter and calling Anthropic directly (different auth, submit-then-poll, not a parameter tweak) -- not built, since it's a real harness change, not a config change.

Also directly tested whether the failure is fixable within the current setup: re-ran the exact trace that already failed with (a) `effort: max` vs `effort: high` (the model's own documented default) and (b) an explicit prompt instruction telling the model it has a hard budget and should conclude with its answer rather than keep checking. **Both attempts failed identically** -- `finish_reason: length`, 128,000/128,000 tokens used, zero visible content, ~9,300-10,000 reasoning tokens either way, $3.55 either way. Neither raising effort nor asking the model to self-regulate its budget changes the outcome. Likely mechanism: `claude-opus-4.8` doesn't support the "extended thinking" mode `claude-opus-4.6` used (an explicit, separate hidden-reasoning budget); it uses a newer "adaptive thinking" mode that doesn't appear to respond to `effort` the same way, and it generates exhaustively regardless of being told to wrap up. This is treated as the final finding for `claude-opus-4.8` under the current (OpenRouter, synchronous) setup, not spent on further without Ram's go-ahead to build the Anthropic-direct Batch API path.

## Do verification scaffolds help? (pilots only, not full runs)

The "promise" test: if raw self-verification is weak, does *forcing the model to show its arithmetic* fix it? Two scaffold variants were built and **piloted** (never run at full n=84) against the two models that showed nonzero the raw-trace run (max effort) detection (`claude-opus-4.6`, `gpt-5.5`), same 84 seeded traces, same binary base, same max-effort settings -- only the prompt (and, for 2b, an output cap) changed:

- **the unbounded-scaffold pilot (unbounded scaffold)** -- prompt forces full digit-by-digit carry-chain arithmetic on *every* addition in *every* round. Pilot: gpt-5.5 caught the easy early tamper cheaply (TP_r4r) but the scaffold **drowned `claude-opus-4.6`** -- it wrote carry-chains until it hit its 128k output cap and returned UNPARSEABLE / missed the tamper, at ~$3.4/call. Extrapolated full cost ~$355-425. Not run.
- **the bounded-scaffold pilot (bounded scaffold)** -- two-pass prompt (triage <=5 suspicious rounds, then carry-chain *only those*) plus a **32k output cap** to stop the drowning. Pilot (6 traces x 2 models, $13.68): **the cap broke both models.** `claude-opus-4.6` went 6/6 UNPARSEABLE (its visible two-pass writeup alone eats 32k before the answer; reasoning was only ~4-5k). `gpt-5.5` went 3/6 UNPARSEABLE + 2 FN + 1 TP_wrong_round = 0 r4r (its UNPARSEABLE cases spent ~28-30k tokens on *hidden max-effort reasoning*, leaving nothing for the visible answer). A 32k cap is fundamentally incompatible with max-effort here. Extrapolated full cost ~$192, but for ~75-100% UNPARSEABLE (near-zero signal) -- **not run** (the pilot failed the "opus stays under cap" precondition the full run was gated on).

### Raw-trace run vs scaffold comparison, right-for-right-reason, per model

TP_r4r = tamper caught AND correct round named (out of 42 tampered). FP = genuine trace false-flagged as tampered (out of 42 genuine). UNPARSE = no parseable answer (budget-exhaustion). **The raw-trace run at max effort is the baseline.**

| Config | Model | TP_r4r (tampers caught) | FP (genuine false-flag) | UNPARSE | n |
|---|---|---|---|---|---|
| raw-trace run (medium, no scaffold) | opus-4.6 | 1/42 | 2/42 | 11 | 84 (full) |
| **raw-trace run (max, no scaffold) — BASELINE** | **opus-4.6** | **8/42 (19%)** | **0/42** | 7 | 84 (full) |
| **raw-trace run (max, no scaffold) — BASELINE** | **gpt-5.5** | **5/42 (12%)** | **8/42 (19%)** | 0 | 84 (full) |
| the unbounded-scaffold pilot (unbounded scaffold) | gpt-5.5 | 1/4* | 0/1* | 0 | 4 (pilot) |
| the unbounded-scaffold pilot (unbounded scaffold) | opus-4.6 | 0/2* | — | 1 | 2 (pilot) |
| the bounded-scaffold pilot (bounded scaffold, 32k cap) | gpt-5.5 | 0/5* | —** | 3 | 6 (pilot) |
| the bounded-scaffold pilot (bounded scaffold, 32k cap) | opus-4.6 | 0/5* | 0/1**→UNPARSE | 6 | 6 (pilot) |

\* pilot slices (small n), not comparable at face value to the full-n baseline; shown to convey direction only. \*\* the single genuine trace in each 2b pilot scored UNPARSEABLE, so no FP could even be measured.

**Verdict: neither scaffold is a "better scaffold helps" result. The raw-trace run at max effort remains the honest finding.** The unbounded scaffold drowns the strongest detector (opus); the bounded-at-32k scaffold makes *both* models strictly worse than no scaffold (opus 8/42 → 0 usable, gpt-5.5 5/42 → 0 r4r + new UNPARSEABLE the baseline didn't have). Forcing arithmetic either exhausts the output budget (opus) or collides with the hidden reasoning budget under a cap (gpt-5.5). The post should NOT claim a scaffold rescues self-verification; if anything the scaffolds are evidence the failure is not merely "the model didn't bother to check carefully." A cleaner intervention (a redesign) is being scoped rather than pushing this variant to full n=84.

## The checkable-rendering redesign (dual rendering + JSON audit, N=84 x 5 models)

Full design + pre-registration in `redesign-proposal.md`. Hypothesis: **the binding
constraint in the raw-trace run (max effort) was observability and error-compounding, not model
capability.** the checkable-rendering redesign keeps the irreducible core (the model must do the arithmetic
itself) but removes every failure that is presentation, not capability:

- **Dual rendering** (`render_dual()` in `sha256_trace.py`): additions in DECIMAL
  (the arithmetic channel LLMs are most reliable in), bitwise ops in binary, state
  words in both; both bases come from the same integer so they always agree. Every
  printed equation is checkable from operands printed on earlier lines -- the tamper
  is EXACTLY ONE locally inconsistent line (the tampered round's `new_a`), verified
  over all 84 traces (`stage0_render.py`). Measured 56.6k trace tokens (vs 63.1k
  binary-only), i.e. a net REDUCTION.
- **Short 5-rule prompt, no scaffold** (`prompt_template_v2.md`): local-check rule
  (compare against printed, never chain your own value), recheck-before-flagging
  rule, check-everything, and an OUTPUT CONTRACT that moves all arithmetic into the
  private reasoning channel and bounds the visible output to a JSON object plus the
  fixed final block -- so the visible output cannot drown (the raw-trace run (max effort)/2's opus killer).
- **Bounded JSON audit layer** (`score_v2.py`): the model reports its own computed
  sum for each of 448 additions, so we measure the raw per-addition arithmetic error
  rate and copy-cheat rate offline against ground truth. JSON keys (`call`/`tamper_r`)
  avoid the `VERDICT:`/`ROUND:` substrings so a malformed JSON cannot collide with the
  final-block parser (self-tested).
- **Harness**: `inspect_task_v2.py` (Inspect), native `cache=True` so a rerun is a
  FREE zero-new-call replay; `.eval` logs capture full input/output/reasoning; every
  lever is a `-T` parameter; full provenance per sample (model, ECI, effort, tokens,
  renderer, seed, git commit, exact api model id).

**Pilot gates (all PASSED before the full run):** Stage 1 gpt-4o parse 7/8; Stage 2
gpt-5 real-computation (8/8 full JSON, 0.11% arithmetic error over 3584 sums; the
JSON exposed a copy-the-transcript laziness that drives its misses); Stage 3 KEY gate
opus-4.6 length-cap UNPARSEABLE 1/6 (the unbounded-scaffold pilot was 6/6 -- the bounded contract fixed
it). Probes dropped per the rule (both must parse): `claude-opus-4.8` 1/2 (one genuine
drowned), `claude-fable-5` 0/2 (still refuses the new framing).

### Redesign result (real, N=84/model main run, dual rendering, max effort)

**The hypothesis is confirmed: the binding constraint in the raw-trace run (max effort) was observability and error-compounding, not model capability.** Reformatting the SAME 84 traces for checkability (decimal arithmetic + local-check rule + bounded JSON audit) moves mechanism-aware detection from a 19% ceiling to 100% for the strongest model, and detection now scales with capability (ECI).

| Model | ECI | Detection (TP_r4r) | Specificity (TN) | UNPARSE (genuine) | AUROC (95% CI) | Brier | Per-addition arith-error |
|---|---|---|---|---|---|---|---|
| `gpt-4o` | 129.3 | 0/42 (0%) | 24/42 (57%; 18 FP) | 0 | 0.470 (0.364-0.579) | 0.512 | 0.17% |
| `o3` | 147.1 | 0/42 (0%) | 39/42 (93%; 3 FP)\* | 0\* | 0.461 (0.340-0.581)\* | 0.404\* | (barely populated JSON) |
| `gpt-5` | 150.0 | **22/42 (52%)** | 41/42 (98%) | 0 | 0.798 (0.699-0.888) | 0.214 | 0.05% |
| `claude-opus-4.6` | 155.5 | **42/42 (100%)** | 42/42 (100%; 0 FP)\* | 0\* | 1.000 (1.000-1.000) | 0.004\* | 0.000% (0/37,632)\* |
| `gpt-5.5` | 158.5 | **37/42 (88%)** | 39/42 (93%; 3 FP) | 0 | 0.929 (0.869-0.977) | 0.071 | 0.01% |

\* **Completion-run numbers (headline).** The 8 genuine-side UNPARSEABLE samples in this arm (opus-4.6 x6, o3 x2) were resampled once each at the same cap on 2026-07-12 after Ram's instruction to redo mechanical no-verdict failures until they produce a real verdict. All 8 resolved to real verdicts on the first retry; none were filtered. **Before completion (original, imputed p=0.5 for the 6/2 no-verdict samples):** `claude-opus-4.6` specificity 36/42 (86%; 0 FP, 6 UNPARSE), AUROC 1.000 (1.000-1.000), Brier 0.021, arith-error 0.003% (1/34,944); `o3` specificity 38/42 (90%; 2 FP), AUROC 0.445 (0.326-0.568), Brier 0.405. The completed numbers are the ones reported as headline in this table; both versions are on disk (`results_v2_before_completion_20260712.jsonl` = original, `results_v2.jsonl` = completed) and neither overwrites the other's evidence.

AUROC here is computed over the full pool of 84 traces from the model's reported `p_tampered` confidence, with UNPARSEABLE (no-verdict) samples imputed at a neutral 0.5 (see `analyze_v2.py`) -- this imputation now applies to zero opus-4.6/o3 genuine-side samples after the 2026-07-12 completion runs (o3 still has 1 UNPARSEABLE on the tampered side, out of this completion run's scope, still imputed).

**Pre-registered success criteria (specificity >=85% AND detection >=50%): THREE of five models pass** -- `claude-opus-4.6` (100% / 100%), `gpt-5.5` (88% / 93%), `gpt-5` (52% / 98%). In the raw-trace run (max effort) the best model reached 19% detection and NONE passed. `opus-4.6` detects every tamper at every position (early/middle/late all 14/14) with zero false positives and, after the 2026-07-12 completion runs, zero genuine-side misses at all (its 6 UNPARSEABLE output-cap cases all resolved to correct GENUINE verdicts on a same-cap resample -- a stochastic verbosity difference, not a hard capability wall on those particular traces; see the caveat below).

**Two structural non-improvers, reported honestly:** `gpt-4o` has no reasoning channel, so it cannot think through ~700 local checks (0% detection, 18/42 false flags, AUROC below chance) -- it is the run-to-run noise anchor, not a capability data point. `o3` is a genuine anomaly: at `effort: high` it barely populated the audit JSON and detected 0/42 (AUROC 0.461 after completion, still below chance), consistent with it being the worst model in the raw-trace run (max effort) too. Its 2 genuine-side no-verdict cases (one refusal, one self-reported incomplete JSON stub -- neither was an output-cap failure, see the completion-run methodology note below) resolved on resample to 1 correct GENUINE and 1 new false positive (TAMPERED at p=0.60 on a genuine trace), so its specificity moved from 38/42 to 39/42 while its off-trend, near-chance detection story is unchanged. So the ECI scaling is monotone among the models that engage the task (gpt-5 52% -> opus-4.6/gpt-5.5 88-100%), with o3 off-trend.

**Completion-run methodology (2026-07-12), stated precisely because the two models' failures had different causes.** For `claude-opus-4.6`, the 6 genuine-side UNPARSEABLE samples were genuine output-cap exhaustion (`output_tokens=128000` exactly, `stop_reason=max_tokens` in the original `.eval` log) -- but `128000` is already OpenRouter's real `max_completion_tokens` ceiling for this model (verified live against `/api/v1/models`), so there was no higher cap to move to; these were resampled at the same, already-provider-maximum cap, and a persistent max-out on a second attempt would have been reported as a real per-trace length ceiling for that model, filtered with disclosure, not as noise. In fact all 6 resolved on the first resample, using 77k-122k of the 128k budget. For `openai/o3`, the 2 genuine-side UNPARSEABLE samples were NOT output-cap failures (`stop_reason=stop`, 335 and 10,317 of the 100,000-token budget used) -- one was an explicit refusal ("I'm sorry, but I can't carry out that task."), the other a self-reported incomplete JSON stub (`{"error":"partial"}`); both are disclosed verbatim here rather than folded into a generic "output cap" story. Both resolved to real verdicts on the first resample. No prompt or scoring change was made for any resample (would break comparability with the other 76 samples in the arm); the only lever was Inspect's `CachePolicy` cache-busting a byte-identical (model, prompt, config) call into a genuinely new one. One caveat on the method itself: resampling conditions on completions that happen to finish within budget, so a model that usually blows the budget on a given trace would look better here than a single random draw would suggest; in this run all 8 resolved on the first retry with no cherry-picking across multiple attempts, but the bias is structurally present in the method. Full per-sample table, cost, and file provenance: `COMPLETION_RUNS.md`.

**Attribution control (control run) -- decisive.** `gpt-5.5` on the OLD binary rendering with the identical new prompt + JSON schema (n=28): detection collapses to **3/14 (21%)** and its per-addition arithmetic-error rate jumps to **3.6%** (vs **0.01%** on the dual/decimal rendering, a ~270x reduction: exact rates 3.637% vs 0.013%). Since only the rendering changed, this attributes essentially the entire gain to **decimal arithmetic** -- the exact failing operation from the raw-trace run (max effort) (carry slips in binary/hex mental math). The JSON audit layer makes the mechanism visible: models compute decimal sums almost perfectly and catch the single inconsistent line; in binary they slip carries, and one slip either misses the tamper or (on genuine traces) manufactures a false flag.

**The raw-trace run (max effort) -> the checkable-rendering redesign, same 84 traces** (`plots/phase1b_vs_phase3_r4r.png`): gpt-4o 0->0, o3 1->0, gpt-5 0->22, opus-4.6 8->42, gpt-5.5 5->37 (out of 42). Scaling plots: `plots/detection_r4r_vs_eci_v2.png`, `plots/specificity_vs_eci_v2.png`.

**Honest framing (from the proposal's validity section):** this is the MAXIMAL-OBSERVABILITY bound -- "can a frontier model verify a trace rendered for checkability," not "will it spontaneously verify any trace." A second bound in the same direction: the tampers are seeded single-bit flips spread across position buckets, NOT adversarially optimized against the verifier; nobody searched for the round a given model finds hardest to check, and a real adversary can iterate tamper placement against a fixed model until it finds blind spots. An adversarial-tamper arm is the natural follow-up. In a real TEE deployment the protocol designer chooses the attestation format, so the format-optimized number is the deployment-relevant one; the raw-trace run (max effort) remains the number for adversarially/carelessly formatted traces. Both are reported.

**Total spend: $475.92** (original the main run/B run $458.80, under the $560 hard cap, plus the 2026-07-12 completion-run resamples $17.12 -- see the completion-run note above), computed = tokens x live prices as of 2026-07-11/2026-07-12 (Inspect logs store tokens, not cost): opus-4.6 $231.48 ($214.61 + $16.87 completion), gpt-5.5 $176.86 (the main run + the control run), gpt-5 $31.43, gpt-4o $17.46, o3 $12.51 ($12.25 + $0.26 completion), probes opus-4.8 $5.49 + fable-5 $0.71.

## Reproduce

- `sha256_trace.py`: deterministic, seeded trace generator + tamper injector. Self-tested against `hashlib.sha256` (`python3 sha256_trace.py`).
- `score.py`: parsing (last VERDICT/ROUND match, robust to empty/None model responses) + r4r scoring logic. Self-tested (`python3 score.py`).
- `run_experiment.py`: the harness.
  - `python3 run_experiment.py --dry-run` -- exact token counts for every format/length combo, zero network calls.
  - `python3 run_experiment.py --ablate-format 5 --assert-cached` / `--ablate-length 5 --base binary --assert-cached` -- reruns the two the format ablations ablations (cheap model only, n=5/bucket = 30 traces/ablation, the actual historical size). `--assert-cached` makes this a genuine zero-new-API-call replay (fails loudly if any cache entry is missing); omitting it re-derives the dataset from the same seeds and still hits 100% cache, but without the hard guard.
  - `python3 run_experiment.py --live --base binary` -- the full 84-trace x 4-model medium-effort run reported above. Already run and cached; **a rerun makes zero new API calls and reproduces `results.jsonl` exactly** (verify with `--assert-cached`, see below).
  - `python3 run_experiment.py --assert-cached --base binary` -- reruns the raw-trace run (medium effort) in cache-only mode and exits with an error if it would need to hit the network, proving the committed cache fully reproduces the reported result.
  - `python3 run_experiment.py --pilot-max-effort 8 --base binary` -- the n=8 x 7-model max-effort pilot (includes `claude-fable-5` and `claude-opus-4.8`), writes to `results_maxeffort_pilot.jsonl` (a separate file from the live run's, see below). Already run and cached; a rerun makes zero new API calls.
  - `python3 run_experiment.py --live-max-effort --base binary` -- the full 84-trace x 5-model max-effort run reported above (`claude-fable-5` and `claude-opus-4.8` excluded per their pilot results). Already run and cached; a rerun makes zero new API calls and reproduces `results_maxeffort.jsonl` exactly (verify with `--assert-cached-max-effort`).
  - `python3 run_experiment.py --assert-cached-max-effort --base binary` -- reruns the raw-trace run (max effort) in cache-only mode, proving the committed cache fully reproduces the reported result (confirmed: zero missing cache entries).
  - `python3 run_experiment.py --phase2 --pilot 4 --phase2-pilot-model eci_159_gpt55 --base binary` (and a `pilot_indices=[42,56]` opus probe) -- the unbounded-scaffold pilot (gpt-5.5 x4 + opus x2, tag `phase2-binary-64`, uses `prompt_template_phase2.md`). Already run and cached; a rerun makes zero new API calls. `--phase2 --live --base binary` would run the full (never-run) 84x2 scaffold.
  - `python3 run_experiment.py --phase2b --pilot 6 --base binary` -- the bounded-scaffold pilot (6 traces x {opus-4.6, gpt-5.5}, tag `phase2b-binary-64`, uses `prompt_template_phase2b.md`, 32k output cap via `--phase2b-max-tokens`). Already run and cached; a rerun makes zero new API calls. The full `--phase2b --live` was **not** run (pilot showed the 32k cap yields ~75-100% UNPARSEABLE for both models).
- Every API response is cached to `cache/<hash>.json`, keyed on `(model, exact prompt text, sample index, tag)` -- `tag` differs by phase (`main-...` vs `maxeffort-...`) so the two phases never collide, and the exact prompt and response for any real call made in this experiment can be inspected directly. Cache entries written from 2026-07-07 onward also store the full raw prompt text, the model's reasoning/thinking content (`message.reasoning`/`message.reasoning_details`), and any refusal text -- entries from the raw-trace run (medium effort) (before that date) only have `{model, prompt_hash, response, usage}` (see `pseudocode.md`'s "Known gap" section).
- `results.jsonl`: the raw-trace run (medium effort)'s 336 scored outcomes. `results_maxeffort.jsonl`: the raw-trace run (max effort)'s 420 scored outcomes. `results_maxeffort_pilot.jsonl`: the 7-model pilot's 56 scored outcomes (a separate file on purpose -- pilot and live modes used to share one filename, and a pilot rerun silently overwrote the live result once; fixed in `run_variant()`, see `pseudocode.md`). Same schema, one line per (model, trace) pair.
- `example_trace_full.txt`: one complete, real, untruncated prompt exactly as sent to a model (binary format, line-numbered, decomposed arithmetic, 64-round genuine-schedule trace with an early-bucket tamper), for direct inspection without running any code.
- `plots/tp_r4r_vs_eci.png`, `plots/tp_r4r_vs_horizon.png`: right-for-right-reason rate vs Epoch Capability Index and vs METR time horizon (real + ECI-estimated), generated from the exact per-model counts in the tables above.
- `plots/cost_vs_accuracy_pareto.png`: real per-call cost vs detection rate for the 5 live-run models, with the Pareto frontier computed directly (not eyeballed).
- `plots/tp_r4r_vs_horizon_pareto.png`: same horizon-vs-detection data as `tp_r4r_vs_horizon.png`, with the Pareto frontier drawn as a dashed trend curve and dominated models marked. Regenerate with `python3 plots/make_pareto_horizon_plot.py` (embeds the same n=42 counts as the table above; no API calls).
- The harness makes concurrent API calls (`ThreadPoolExecutor`, `MAX_WORKERS=16` in `run_experiment.py`) since `claude-opus-4.6`/`gpt-5.5`/`claude-opus-4.8` completions can take 10+ minutes each at max effort; this only affects wall-clock time, not which calls get made or their results.
- Full setup and control-flow diagrams (mermaid): `pseudocode.md`.
- `inspect_task.py`: the Inspect (`inspect_ai`) port of the raw-trace run (max effort), reusing `build_dataset`/`build_prompt`/`render_trace`/`score.py` directly. One model at a time (each needs its own `reasoning_effort`/`max_tokens`):
  - `inspect eval inspect_task.py --model openrouter/openai/gpt-4o -T model_key=openai/gpt-4o --log-dir logs_inspect`
  - `inspect eval inspect_task.py --model openrouter/openai/o3 -T model_key=openai/o3 --log-dir logs_inspect`
  - `inspect eval inspect_task.py --model openrouter/openai/gpt-5 -T model_key=openai/gpt-5 --log-dir logs_inspect`
  - `inspect eval inspect_task.py --model openrouter/anthropic/claude-opus-4.6 -T model_key=anthropic/claude-opus-4.6 --log-dir logs_inspect`
  - `inspect eval inspect_task.py --model openrouter/openai/gpt-5.5 -T model_key=openai/gpt-5.5 --log-dir logs_inspect`
  - Already run; logs are committed... no, `.eval` logs are large (up to ~107MB each) and not committed to git -- see `logs_inspect/.gitignore` if present, otherwise treat them as local artifacts. Re-running any of the 5 commands above makes new API calls (Inspect has no cache-replay mode analogous to `--assert-cached`); there is no free-replay path for this harness.
  - `inspect view --log-dir logs_inspect` -- browse the full transcript (input, output, and native reasoning content) for any sample in any of the 5 runs.
  - `python3 summarize_inspect_logs.py` -- recomputes the TN/TP_r4r/TP_wrong_round/FP/FN/UNPARSEABLE table from the `.eval` logs (handles the `claude-opus-4.6` `reasoning_effort="max"` pydantic bug via a raw-zip fallback, see below).

### Checkable-rendering redesign -- exact reproduce, in order

Every command below is copy-paste runnable from a clean checkout with `OPENROUTER_API_KEY` set. Cache key note: Inspect's `cache=True` keys on model + prompt + generate-config; editing `prompt_template_v2.md` or `render_dual()` orphans the cache (a full re-spend), so the free replay holds only while those are unchanged.

1. **Regenerate the traces + prove the invariant (zero API):** `python3 sha256_trace.py` (generator vs `hashlib`), `python3 stage0_render.py` (writes `artifacts/example_*_dual.txt`, proves the tampered `new_a` is the only inconsistent line over all 84 traces).
2. **Self-tests (zero API), must pass before any spend:** `python3 score.py` and `python3 score_v2.py` (8 audited bug classes + AUROC/TPR/Brier hand-checks).
3. **Dry-run token count:** `python3 sha256_trace.py --dry-run` (reproduces the ~56.6k trace / ~57.6k prompt measurement).
4. **Main run, full run (5 committed models, N=84, dual, max effort)** -- one `inspect eval` per model (each needs its own effort/cap, read from `run_experiment.py` by `model_key`):
    - `inspect eval inspect_task_v2.py --model openrouter/openai/gpt-4o -T model_key=openai/gpt-4o --log-dir logs_inspect_v2 --max-connections 30`
    - `inspect eval inspect_task_v2.py --model openrouter/openai/o3 -T model_key=openai/o3 --log-dir logs_inspect_v2 --max-connections 30`
    - `inspect eval inspect_task_v2.py --model openrouter/openai/gpt-5 -T model_key=openai/gpt-5 --log-dir logs_inspect_v2 --max-connections 30`
    - `inspect eval inspect_task_v2.py --model openrouter/anthropic/claude-opus-4.6 -T model_key=anthropic/claude-opus-4.6 --log-dir logs_inspect_v2 --max-connections 30`
    - `inspect eval inspect_task_v2.py --model openrouter/openai/gpt-5.5 -T model_key=openai/gpt-5.5 --log-dir logs_inspect_v2 --max-connections 30`
5. **Control run (attribution control): gpt-5.5, OLD binary rendering + NEW prompt+schema, n=28:** `inspect eval inspect_task_v2.py --model openrouter/openai/gpt-5.5 -T model_key=openai/gpt-5.5 -T renderer=binary -T balanced_n=28 --log-dir logs_inspect_v2 --max-connections 30`
6. **Pilot slices (already covered by cache above):** add `-T pilot_n=8` (Stage 1/2), `-T pilot_n=6` (Stage 3 opus-4.6/gpt-5.5), `-T pilot_n=2` (probes: `anthropic/claude-opus-4.8`, `anthropic/claude-fable-5`).
7. **ZERO-NEW-CALL REPLAY (the reproducibility gold standard):** re-run any the main run/B command above -- Inspect serves every sample from cache, making **zero new API calls** -- then `python3 analyze_v2.py --gates` re-derives `results_v2.jsonl` and every headline number (metric suite, AUROC + bootstrap CIs, per-position, per-addition error rate, cost) identically. Proof of the zero-call replay is in `artifacts/replay_zero_calls.txt`.
8. **Regenerate results, metrics, and plots from the logs (zero API):** `python3 analyze_v2.py --gates` (writes `results_v2.jsonl` + the full metric table + cost) and `python3 make_plots_v2.py` (writes `plots/detection_r4r_vs_eci_v2.png`, `plots/specificity_vs_eci_v2.png`, `plots/phase1b_vs_phase3_r4r.png`).
9. **2026-07-12 completion runs (the 8 genuine-side no-verdict samples, opus-4.6 x6 + o3 x2, dual arm) -- NOT a free replay, real new calls by design.** `resample_tag` busts Inspect's cache on purpose (see `COMPLETION_RUNS.md` for the per-sample table and why a plain rerun cannot make a new call here):
    - `inspect eval inspect_task_v2.py --model openrouter/anthropic/claude-opus-4.6 -T model_key=anthropic/claude-opus-4.6 -T sample_ids=0,5,10,11,20,28 -T resample_tag=completion-fix-20260712 --log-dir logs_inspect_v2 --max-connections 6`
    - `inspect eval inspect_task_v2.py --model openrouter/openai/o3 -T model_key=openai/o3 -T sample_ids=17,23 -T resample_tag=completion-fix-20260712 --log-dir logs_inspect_v2 --max-connections 6`
    - Re-running these two commands with the SAME `resample_tag` value IS a free zero-new-call replay (the tag makes the config, and therefore the cache key, deterministic again once set); changing `resample_tag` to a new value forces another real resample.
    - `python3 analyze_v2.py --gates` afterward regenerates `results_v2.jsonl` from the logs (dedup keeps the latest-timestamped log per `(model_key, renderer, seed)`), so the completed numbers become the file's content automatically. The pre-completion snapshot is preserved separately at `results_v2_before_completion_20260712.jsonl` and is not touched by this step.

Outputs: `results_v2.jsonl` (one line per (model, renderer, trace) with full provenance, now the COMPLETED/headline version), `results_v2_before_completion_20260712.jsonl` (the ORIGINAL/imputed pre-completion snapshot, kept as a separate artifact), `logs_inspect_v2/*.eval` (full transcripts incl. reasoning, viewable via `inspect view --log-dir logs_inspect_v2`; includes the 2026-07-12 completion-run logs), `artifacts/` (audit layer, indexed by `artifacts/README.md`), `plots/*_v2.png`.

## Status

### Naming: how the run-names in this README map to files and flags

The prose above uses plain descriptive run-names. The data files, plot files, and CLI flags keep their original short tags. This table decodes them so nothing is ambiguous.

| Name used here | Original short tag | Files and flags it corresponds to |
|---|---|---|
| format ablations | Phase 0 | `run_experiment.py --ablate-format` / `--ablate-length` |
| raw-trace run (medium effort) | Phase 1 | `results.jsonl`; `run_experiment.py --live` |
| raw-trace run (max effort) | Phase 1b | `results_maxeffort.jsonl`, `logs_inspect/*.eval`; `run_experiment.py --live-max-effort` |
| unbounded-scaffold pilot | Phase 2 | `results_phase2_pilot*.jsonl`, `prompt_template_phase2.md`; `--phase2` |
| bounded-scaffold pilot | Phase 2b | `results_phase2b_pilot.jsonl`, `prompt_template_phase2b.md`; `--phase2b` |
| checkable-rendering redesign | Phase 3 | `results_v2.jsonl`, `logs_inspect_v2/*.eval`, `inspect_task_v2.py`, `prompt_template_v2.md`, `*_v2.png`, `phase1b_vs_phase3_r4r.png` |
| main run | Arm A | the 5-model, N=84, dual-rendering run in the redesign |
| control run | Arm B | the gpt-5.5, old-binary-rendering attribution control (n=28) |

**Complete through the checkable-rendering redesign.** The format-selection ablations, the full raw-trace run at medium effort (4 models), and the full raw-trace run at max effort (5 models + a pilot that surfaced `claude-fable-5`'s 100% refusal) are all done via the raw harness, real API calls, real total cost $686.53. A second, independent replication of the raw-trace run (max effort) via Inspect (`inspect_ai`) is also complete, ~$449.79 (estimated), summarized above. **The unbounded-scaffold pilot and the bounded-scaffold pilot (32k output cap) were PILOTED only ($24.45 combined) and NOT taken to full n=84** -- both pilots showed the scaffold makes the two target models worse, not better (see "Do verification scaffolds help?" above), which motivated the checkable-rendering redesign instead of a scaffold. **The checkable-rendering redesign (dual decimal/binary rendering + bounded JSON audit, N=84 x 5 models main run + n=28 control-run attribution control) is COMPLETE, real cost $458.80** -- see "The checkable-rendering redesign" above for the full result: detection moves from a 19% ceiling (the raw-trace run (max effort)) to 100%/88%/52% for opus-4.6/gpt-5.5/gpt-5, three of five models pass the pre-registered bar, and the control run attributes the gain to the decimal rendering, not model capability. **2026-07-12: completion-run resamples ($17.12) resolved all 8 genuine-side no-verdict samples in the dual arm (opus-4.6 x6, o3 x2) to real verdicts, none filtered** -- opus-4.6 specificity moves from 36/42 (imputed) to 42/42 (100%, all-correct); o3 specificity moves from 38/42 (imputed) to 39/42; both-ways numbers in the checkable-rendering redesign table's footnote above. The pre-completion state is preserved in `results_v2_before_completion_20260712.jsonl`; the headline `results_v2.jsonl` is the completed version. **Total project spend: ~$1,637.** Results are in `results.jsonl` (the raw-trace run (medium effort)), `results_maxeffort.jsonl` (the raw-trace run (max effort)), `logs_inspect/*.eval` (Inspect redo), `results_phase2_pilot*.jsonl` / `results_phase2b_pilot.jsonl` (scaffold pilots), and `results_v2.jsonl` / `logs_inspect_v2/*.eval` (the checkable-rendering redesign, including the 2026-07-12 completion-run logs).

### Inspect redo: cross-validating the max-effort raw-trace run on a second, independent harness

A full redo of the raw-trace run (max effort) live run (same 5 models, same 84-trace dataset, same reasoning-effort/max-tokens settings, same `score.py` r4r rule) via UK AISI's Inspect (`inspect_ai`), using `inspect_task.py` instead of the raw-harness request loop, so the same result is also available as standard, viewable `.eval` logs: `inspect view --log-dir logs_inspect`. This was a second, real ~$450 re-spend on the same underlying calls (see cost table below) -- not new experimental ground, but a genuine independent replication: every model was called a second time against the identical prompts, through different client code.

| Model | TP_r4r (raw harness) | TP_r4r (Inspect) | Cost (raw harness, exact) | Cost (Inspect, estimated) |
|---|---|---|---|---|
| `gpt-4o` | 0/42 (0.0%) | 0/42 (0.0%) | $13.64 | ~$13.56 |
| `o3` | 1/42 (2.4%) | 1/42 (2.4%) | $16.62 | ~$16.88 |
| `gpt-5` | 0/42 (0.0%) | 3/42 (7.1%) | $21.27 | ~$26.45 |
| `claude-opus-4.6` | 8/42 (19.0%) | 6/42 (14.3%) | $253.03 | ~$262.44 |
| `gpt-5.5` | 5/42 (11.9%) | 5/42 (11.9%) | $122.64 | ~$130.46 |
| **Total** | | | **$427.19** | **~$449.79** |

The Inspect cost column is a list-price estimate (input/output token totals from `EvalLog.stats.model_usage` x live OpenRouter per-token pricing), not a recorded per-call `usage.cost` like the raw-harness figures -- Inspect's OpenRouter provider doesn't populate a per-call cost field the way our custom harness's direct API parsing did.

**3 of 5 models reproduced their TP_r4r count exactly** (`gpt-4o`, `o3`, `gpt-5.5`) on a second, independent call through different client code -- real evidence the headline numbers aren't a harness artifact. **2 of 5 moved**: `gpt-5` went from 0 to 3/42 (more willing to both flag and correctly place a tamper this time) and `claude-opus-4.6` went from 8 to 6/42 (down two). Both are within the kind of run-to-run sampling variance already flagged for `gpt-4o`'s false-positive rate elsewhere in this document (a second call to the same prompt at "max"/"xhigh" reasoning effort is not deterministic) -- not evidence against the original result, but a concrete measurement of how much this eval's numbers can move on a bare rerun.

**A real bug in `inspect_ai` 0.3.189, found and worked around, not hidden:** the `claude-opus-4.6` run (the only one using `reasoning_effort="max"`) completed all 84 samples successfully, then crashed on `log_finish` with `ValueError: Attempt to write to ZIP archive that was already closed`. Root cause: `GenerateConfig.reasoning_effort` accepts `"max"` for making the actual API call, but the *persisted* `EvalLog.plan.config` schema's `Literal` type does not include `"max"` (only `none/minimal/low/medium/high/xhigh`) -- so `read_eval_log()` raises a pydantic `ValidationError` on any log that used `effort="max"`. Confirmed the `.eval` file itself is not corrupted (`zipfile.testzip()` passes, all 84 sample JSON entries are present); `summarize_inspect_logs.py` falls back to reading the raw sample JSON directly out of the zip for this one file, bypassing the strict pydantic path entirely. No data was lost and no extra API spend was needed to recover it.

The unbounded-scaffold pilot (the verification-scaffold "promise" test) was subsequently built and piloted (see "Do verification scaffolds help?" above) -- both pilots showed the scaffold makes the two target models worse, not better, which motivated the checkable-rendering redesign (dual rendering + bounded JSON audit, no scaffold) instead of taking either scaffold to a full n=84 run. The checkable-rendering redesign is the current, complete result.
