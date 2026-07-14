# Can AI models verify cryptographic traces?

The reproducibility package for the LessWrong post **"Making Credible Deals With AI"** by Ram Potham. It measures whether a frontier language model can catch a single flipped bit hidden inside a cryptographic computation trace and name the exact step where it was flipped. That is the load-bearing empirical question behind the post's claim that an AI could verify a hardware attestation by re-deriving it in its own reasoning, with no tool calls.

**Confidence: High on the detection result, Medium-to-Low on the frontier dates.** The detection numbers are real API calls, fully reproducible with a proven zero-new-call replay. The frontier horizon is fit on small samples and an easier proxy, so its dated crossings are an optimistic upper bound, not a calendar commitment (see below).

Everything here reproduces from committed code, per-call caches, and Inspect `.eval` logs. A rerun makes zero new API calls and reproduces every table.

## The two headline results

### 1. Detection is weak on a raw trace, strong on a trace rendered to be checked

Give a model a full SHA-256 computation trace, genuine or with exactly one bit flipped and everything downstream recomputed consistently, and ask it to find the flip. Scoring is strict: a `TAMPERED` verdict counts only if the model also names the exact tampered round. "Something is wrong somewhere" is a miss.

**On a raw trace the AI is simply handed, the best model catches 19% of tampers, and it fails in both directions.** It misses real tampers and it false-flags genuine traces, both from carry errors it makes while doing its own binary arithmetic.

Raw trace, max reasoning effort, n=42 tampered and 42 genuine per model:

| Model | Tamper caught (exact round) | Genuine false-flagged |
| --- | --- | --- |
| gpt-4o | 0/42 (0%) | 20/42 (48%) |
| o3 | 1/42 (2.4%) | 3/42 (7%) |
| gpt-5 | 0/42 (0%) | 13/42 (31%) |
| gpt-5.5 | 5/42 (11.9%) | 8/42 (19%) |
| claude-opus-4.6 | **8/42 (19%)** | 0/42 (0%) |

**Rendering the same 84 traces to be checked broke the 19% ceiling.** Show every addition in decimal, make each check a local comparison against a value printed just above rather than a chained re-derivation, and bound the visible output so no model drowns. Same traces, same strict scoring, so this is a controlled before-and-after on presentation alone.

Checkable rendering, same 84 traces, n=42 tampered and 42 genuine per model:

| Model | ECI | Tamper caught (exact round) | Genuine passed | AUROC |
| --- | --- | --- | --- | --- |
| gpt-4o | 129 | 0/42 (0%) | 24/42 (57%) | 0.47 |
| o3 | 147 | 0/42 (0%) | 39/42 (93%) | 0.46 |
| gpt-5 | 150 | 22/42 (52%) | 41/42 (98%) | 0.80 |
| claude-opus-4.6 | 155 | **42/42 (100%)** | **42/42 (100%)** | 1.00 |
| gpt-5.5 | 158 | 37/42 (88%) | 39/42 (93%) | 0.93 |

**Three of five models clear the pre-registered bar** (at least 85% of genuine traces passed and at least 50% of tampers caught): gpt-5, gpt-5.5, and opus-4.6. On the raw trace, none did. Detection now scales with capability among the models that engage the task. gpt-4o has no reasoning channel and o3 barely engaged the audit, so both stay near chance; the rendering lets a model that can reason through the checks do so, and does not conjure verification out of nothing.

**The gain is the rendering, not the instructions.** A control run confirms it: gpt-5.5 on the old binary rendering with the identical new prompt collapses back to 3/14 (21%). Its per-addition arithmetic error rate is 3.6% in binary versus 0.01% in decimal, over two orders of magnitude fewer slips. The decimal rendering is what removes the carry errors that were compounding into both missed tampers and false flags.

**What this means for the post.** The failure on a raw trace is presentation and error-compounding, not model capability. The honest party in a deal chooses the attestation format, so it can always render for checkability. The 19% number stays the number for adversarial or careless formats; a trace built to be checked is a different story.

### 2. The verification horizon over time, measured on a proxy

How long a cryptographic trace can a model verify before compounding errors defeat it? [`verification-frontier/`](verification-frontier/) measures the **N90 horizon: the trace length, in word-level operations, at which a model stays right nine times in ten on a tamper check.** This is the exact-verification analog of METR's time horizons. N90, not N50, is the deployment-relevant bar, because a coin-flip verifier is worse than none: a check that wrongly passes a fake leaves the AI more confident in the fake than if it had never checked.

**The horizon is fit on a small-curve / SHA proxy axis, and real P-256 diverges harder.** Real 256-bit P-256 arithmetic is measurably harder than the same computation over a small curve at matched length, and the two do not overlay. On real P-256, today's models already collapse to about 0% detection by a few hundred operations, far short of the small-curve horizon. So the dated crossings below are an **optimistic upper bound read off the easier proxy, not a measurement on the real primitive.**

Measured points (small cells, 2 to 8 traces each, so directional):

| Model | Small-curve / SHA horizon | On real P-256 |
| --- | --- | --- |
| o3 | N50/N90 bracketed 321 to 448 ops | already 0% by ~202 to 270 ops |
| gpt-5 | N50 ~448 ops, N90 ~415 ops (90% CI [24, 422]) | already 0% by ~470 ops |
| claude-opus-4.6 | 100% through ~896 ops | drops to 0% by ~2,024 ops (first real bound) |

gpt-4o never clears the bar on either family and is left off the trend.

**On the proxy trend, the N90 horizon roughly doubles every 154 days**, and reaches full ECDSA-signature length (about 410,000 to 800,000 operations) around **2029-11** and a full TEE attestation check (roughly 1.2 to 3.2 million operations) around **2030-08**. These are extrapolations from three points over small samples, two of them brackets rather than sharp crossings, and read off the easier proxy. Treat the dates as order-of-magnitude, and as an optimistic upper bound: the real-P-256 frontier today is much shorter.

## Design

**Task.** The model receives a full SHA-256 computation trace: the message, the message schedule W[0..63], and all 64 compression rounds with every intermediate operand shown (S1, ch, temp1, S0, maj, temp2 spelled out, not just the post-round summary). The trace is either genuine or has exactly one bit flipped at one intermediate value, with everything downstream recomputed consistently from that point, so the trace stays self-consistent and there is no local arithmetic glitch to spot. The only way to catch it is to re-derive the arithmetic. No tool calls, matching the post's claim that this should be checkable in chain-of-thought alone.

**Two renderings of the same 84 traces.** The raw rendering shows every addition as a 32-bit binary carry chain. The checkable rendering shows every addition in decimal alongside the binary, makes each check a local comparison against a printed value, and bounds the visible output to a JSON audit object plus a fixed verdict block. Both bases come from the same integer, so they always agree; only the presentation differs.

**Sample size and scoring.** 14 traces per position bucket (early, middle, late) per condition, 42 genuine plus 42 tampered per model, fixed before running. Right-for-right-reason scoring: a `TAMPERED` verdict counts only if the model names the correct round. At n=42, single-run percentages are directional, not precise.

**Models.** gpt-4o, o3, gpt-5, claude-opus-4.6, gpt-5.5, spanning ECI 129 to 158. claude-fable-5 refuses this task outright (8/8, cyber-content policy block) and is excluded.

## Example trace (real output, truncated)

This is actual output of `src/sha256_trace.py`, not a mockup. The full untruncated prompt as sent to a model is in `review/full_prompt_example.txt`.

The raw rendering makes every check a 32-bit carry chain:

```
L0072: step1 = h + S1 mod 2^32 = 1001 0001 0110 0111 1111 0100 0100 0100
L0073: step2 = step1 + ch mod 2^32 = 1011 0000 1110 1101 1011 1101 1101 0000
```

The checkable rendering makes each check one decimal addition against numbers printed right above it. These are the actual lines around the planted error in one tampered trace:

```
L0402: temp1 = step3 + W[16] mod 2^32 = 2602827452
L0405: temp2 = S0 + maj mod 2^32 = 3851614655
L0406: new a = temp1 + temp2 mod 2^32 = ... = 2159474747
```

You can check L0406 with a calculator: 2602827452 + 3851614655 mod 2^32 is 2159474811, not the printed 2159474747. That one line is the only inconsistency in the whole trace; every other line, including everything downstream, checks out. In the binary rendering, finding it means not slipping a single carry across 448 such additions.

## Reproduce

Every command runs from a clean checkout with `OPENROUTER_API_KEY` set. The self-tests and analysis make zero API calls; the `inspect eval` runs are already cached, so a rerun replays from cache for $0 (Inspect keys on model + prompt + config, so editing a prompt template or renderer orphans the cache).

All commands run from the repo root.

```
# 1. Self-tests (zero API calls), must pass before any spend:
python3 src/sha256_trace.py        # generator vs hashlib
python3 src/render_examples.py     # proves the tampered new_a is the only inconsistent line, all 84 traces
python3 src/score.py               # raw-trace r4r scoring self-test
python3 src/score_checkable.py     # checkable-rendering scoring + AUROC/Brier hand-checks

# 2. Raw-trace result (the 19% ceiling), cache-only replay, no network:
python3 src/run_experiment.py --assert-cached-max-effort --base binary   # reproduces results/raw_maxeffort.jsonl

# 3. Checkable-rendering result (the 100% headline), one inspect eval per model.
#    Already cached: a rerun makes zero new API calls.
inspect eval src/inspect_task_checkable.py --model openrouter/openai/gpt-4o             -T model_key=openai/gpt-4o             --log-dir data/logs_checkable --max-connections 30
inspect eval src/inspect_task_checkable.py --model openrouter/openai/o3                 -T model_key=openai/o3                 --log-dir data/logs_checkable --max-connections 30
inspect eval src/inspect_task_checkable.py --model openrouter/openai/gpt-5              -T model_key=openai/gpt-5              --log-dir data/logs_checkable --max-connections 30
inspect eval src/inspect_task_checkable.py --model openrouter/anthropic/claude-opus-4.6 -T model_key=anthropic/claude-opus-4.6 --log-dir data/logs_checkable --max-connections 30
inspect eval src/inspect_task_checkable.py --model openrouter/openai/gpt-5.5            -T model_key=openai/gpt-5.5            --log-dir data/logs_checkable --max-connections 30

# 4. Control run (attribution): gpt-5.5, old binary rendering + the new prompt, n=28:
inspect eval src/inspect_task_checkable.py --model openrouter/openai/gpt-5.5 -T model_key=openai/gpt-5.5 -T renderer=binary -T balanced_n=28 --log-dir data/logs_checkable --max-connections 30

# 5. Regenerate every number and plot from the logs (zero API):
python3 src/analyze_checkable.py --gates      # writes results/checkable.jsonl + the full metric table
python3 src/make_plots_checkable.py           # writes plots/detection_vs_capability.png, specificity_vs_capability.png, raw_vs_checkable_detection.png
```

**Zero-new-call replay** is the reproducibility gold standard here: re-run any `inspect eval` above, Inspect serves every sample from cache, then `src/analyze_checkable.py --gates` re-derives every headline number identically. Proof is in `review/artifacts/replay_zero_calls.txt`.

The verification-frontier horizon experiment (Figure 2 of the post) has its own Reproduce block in [`verification-frontier/README.md`](verification-frontier/README.md).

## What is in this repo

- `src/`: all Python plus the run shell script.
  - `sha256_trace.py`, `render_examples.py`: seeded trace generator, tamper injector, and dual rendering, self-tested against `hashlib`.
  - `run_experiment.py`: the raw-harness request loop (raw-trace runs, cached free replay).
  - `inspect_task.py`, `inspect_task_checkable.py`: the Inspect ports (raw and checkable), one model per run.
  - `score.py`, `score_checkable.py`: parsing and right-for-right-reason scoring, self-tested.
  - `analyze_checkable.py`, `make_plots_checkable.py`, `summarize_inspect_logs.py`: analysis and plots from the logs.
- `prompts/raw_trace.md`, `prompts/checkable.md`: the prompts sent to models.
- `results/raw.jsonl`, `results/raw_maxeffort.jsonl`, `results/checkable.jsonl`: scored outcomes, one line per (model, trace).
- `data/cache/`, `data/logs_raw/`, `data/logs_checkable/`: the per-call cache and Inspect `.eval` logs the zero-new-call replay depends on.
- `plots/`: figures.
- `review/`: the human review layer (`review/README.md` indexes it): `full_prompt_example.txt` (one complete real prompt), `traces/` (curated per-outcome cases), `artifacts/` (one proving artifact per pipeline step).
- `pseudocode.md`: the mechanistic map, with setup and control-flow diagrams.
- `verification-frontier/`: the horizon experiment (Figure 2).
