"""RQ3 replication harness.

Calls models via OpenRouter (OPENROUTER_API_KEY from /home/ram/obsidian/.env).
Every response is cached to disk, keyed on (model, prompt_hash, sample_idx),
so a repeat invocation makes zero new API calls if nothing changed
(`--assert-cached` fails loudly if it would have to call the network).

Modes:
  --dry-run             compute exact token counts for every format/length
                         combo, no network call
  --ablate-format N      (real, cheap-model-only) N traces/condition x
                         {hex, binary} on the cheap model, to pick a format
  --ablate-length N --base X   (real, cheap-model-only) N traces/condition x
                         {64, 16} rounds on the cheap model, given a base
  --pilot N              run N calls per model (main 4-model dataset) as a
                         cost sanity check before committing to the full run
  --live                 run the full main experiment (84 traces x 4 models)
  --assert-cached        rerun in cache-only mode, fail if any call would hit
                         the network (proves full reproducibility)

This script makes no network calls on import or by default. --ablate-*,
--pilot, and --live are the only modes that spend money, and all require
OPENROUTER_API_KEY to be set.
"""

import argparse
import hashlib
import json
import os
import sys

import tiktoken

from sha256_trace import generate_genuine, generate_tampered, render_trace, position_buckets
from score import parse_response, score

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "prompt_template.md")
# Phase 2 (2026-07-11): the verification-scaffold variant. SAME 84 traces, same
# binary rendering, same right-for-right-reason scoring -- only the prompt
# changes (freeform "does this look right" -> explicit written-out carry-chain
# addition at every compression add step). A distinct template file means the
# scaffold prompt text differs, so its cache keys never collide with Phase 1/1b
# even before the distinct tag is applied.
PHASE2_PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "prompt_template_phase2.md")
# Phase 2b (2026-07-11): the BOUNDED verification scaffold. Two-pass prompt
# (triage <=5 rounds, then carry-chain only those) + a capped output budget so
# claude-opus-4.6 can't drown in busywork like it did in Phase 2 (all 64 rounds
# forced -> 128k output cap hit -> UNPARSEABLE). Same 84 traces, same binary
# base, same r4r scoring; only the prompt and the output cap change vs Phase 1b.
PHASE2B_PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "prompt_template_phase2b.md")
# Capped output budget for Phase 2b, well under the 128k that pinned opus. A
# module default; the actual value used is a parameter (--phase2b-max-tokens),
# not hardcoded into the call path.
PHASE2B_MAX_TOKENS = 32000
# Phase 3 (2026-07-11): maximally-observable redesign (see redesign-proposal.md).
# Dual binary+decimal rendering (render_dual), short 5-rule prompt, bounded JSON
# output. Run via inspect_task_v2.py (Inspect, native caching).
PROMPT_TEMPLATE_V2_PATH = os.path.join(os.path.dirname(__file__), "prompt_template_v2.md")

# Epoch Capability Index, pulled from epoch.ai/data/eci_scores.csv (see plan.md
# 2026-07-08 entry). Single source of truth for the capability axis; provenance
# and scaling plots read from here. Snapshot date recorded in PROVENANCE below.
ECI_SCORES = {
    "openai/gpt-4o": 129.3,
    "openai/o3": 147.1,
    "openai/gpt-5": 150.0,
    "anthropic/claude-opus-4.6": 155.5,
    "anthropic/claude-opus-4.8": 158.1,
    "openai/gpt-5.5": 158.5,
    "anthropic/claude-fable-5": 160.8,
}
ECI_SNAPSHOT_DATE = "2026-07-08"  # date the eci_scores.csv values above were pulled

# OpenRouter prices (USD per 1M tokens, input/output), as of PRICES_DATE. Output
# price is billed on visible + reasoning tokens. gpt-5.5 rates are inferred from
# real Phase 1b usage.cost (2026-07-08); the rest are OpenRouter's listed prices.
# Inspect logs store token counts but NOT cost, so cost is computed = tokens*price.
PRICES = {
    "openai/gpt-4o": (2.50, 10.00),
    "openai/o3": (2.00, 8.00),
    "openai/gpt-5": (1.25, 10.00),
    "anthropic/claude-opus-4.6": (5.00, 25.00),
    "openai/gpt-5.5": (2.66, 26.12),
    "anthropic/claude-opus-4.8": (5.00, 25.00),
    "anthropic/claude-fable-5": (5.00, 25.00),
}
PRICES_DATE = "2026-07-11"


def call_cost(model_key, input_tokens, output_tokens):
    """USD cost from token counts and PRICES (Inspect logs lack usage.cost)."""
    pin, pout = PRICES[model_key]
    return input_tokens / 1e6 * pin + output_tokens / 1e6 * pout

# Chosen for published METR 50%-time-horizon values (metr.org/time-horizons),
# not arbitrary cheap/mid/frontier tiers, so detection accuracy can be plotted
# against a model's independently-measured autonomous-task-length capability.
# Slugs and pricing confirmed live against openrouter.ai/api/v1/models; see
# proposal.md / README.md for the horizon values and cost breakdown.
MODELS = {
    "horizon_7min": "openai/gpt-4o",             # ~7 min horizon,   $2.50/$10 per M
    "horizon_120min": "openai/o3",               # ~120 min horizon, $2.00/$8 per M
    "horizon_203min": "openai/gpt-5",            # ~203 min horizon, $1.25/$10 per M
    "horizon_719min": "anthropic/claude-opus-4.6",  # ~719 min horizon, $5.00/$25 per M
}

# Added for the max-effort re-run (2026-07-07), per Ram: Epoch Capability
# Index (epoch.ai/eci) top models as of this date, not a price/horizon pick --
# claude-fable-5 (ECI 161, #1) and gpt-5.5 (ECI 159). claude-opus-4.8 (ECI
# 158) was initially excluded per Ram, then added back 2026-07-08 ("can you
# also try Opus 4.8") -- API-compat-tested (effort=max, 200 OK) before any
# spend; pilot cost data gates whether it joins the full live run.
NEW_MODELS = {
    "eci_161_fable5": "anthropic/claude-fable-5",
    "eci_159_gpt55": "openai/gpt-5.5",
    "eci_158_opus48": "anthropic/claude-opus-4.8",
}
ALL_MODELS = {**MODELS, **NEW_MODELS}  # used for the n=8 pilot only

# claude-fable-5 refused 8/8 pilot traces outright (real API refusal, "violative
# cyber content" per Anthropic's usage policy, not a bug) -- $0.54/call for zero
# usable data. Per Ram, dropped from the full live max-effort run; the pilot
# result (100% refusal) is itself kept and reported as a finding.
LIVE_MAX_EFFORT_MODELS = {**MODELS, "eci_159_gpt55": "openai/gpt-5.5"}

CHEAP_MODEL = MODELS["horizon_7min"]  # used for the ablation search only

# Per Ram: allow enough CoT for the model to actually work the problem, but
# not the maximum/most expensive setting. OpenAI reasoning models take an
# "effort" level (medium ~50% of max_tokens go to hidden reasoning);
# Anthropic models take an explicit reasoning token budget instead.
# gpt-4o has no hidden reasoning channel at all: its "thinking" is whatever
# it writes in the visible completion, so it just needs a generous
# completion max_tokens instead of a reasoning param.
REASONING_PARAMS = {
    "openai/gpt-4o": None,
    "openai/o3": {"effort": "medium"},
    "openai/gpt-5": {"effort": "medium"},
    "anthropic/claude-opus-4.6": {"max_tokens": 4096},
}

# Max-effort re-run (2026-07-07): Ram wants to test whether the near-zero
# Phase 1 result is a genuine capability ceiling or an artifact of the
# deliberately-capped reasoning budget above. "effort" and "max_tokens" are
# mutually exclusive, so this REPLACES the explicit max_tokens=4096 approach
# for Claude models, it doesn't add to it. gpt-4o still has no reasoning
# channel at all, so "max effort" doesn't apply to it.
#
# The actual top effort value is NOT uniform across providers -- confirmed
# empirically (not guessed) by direct API probes, since OpenRouter's own docs
# say "max"/"xhigh" work everywhere and that turned out false for one model:
#   - o3 (the specific `o3-2025-04-16` deployment) rejects both "max" and
#     "xhigh" with a 400: "Supported values are: 'low', 'medium', 'high'."
#     Its real ceiling is "high".
#   - gpt-5 / gpt-5.5 accept "xhigh" (confirmed 200 OK).
#   - claude-opus-4.6 / claude-fable-5 accept "max" (confirmed 200 OK).
MAX_EFFORT_REASONING_PARAMS = {
    "openai/gpt-4o": None,
    "openai/o3": {"effort": "high"},
    "openai/gpt-5": {"effort": "xhigh"},
    "anthropic/claude-opus-4.6": {"effort": "max"},
    "anthropic/claude-fable-5": {"effort": "max"},
    "openai/gpt-5.5": {"effort": "xhigh"},
    "anthropic/claude-opus-4.8": {"effort": "max"},  # confirmed 200 OK, same family as opus-4.6
}
COMPLETION_MAX_TOKENS = {
    # Set to each model's REAL max_completion_tokens (confirmed live against
    # openrouter.ai/api/v1/models' top_provider field, not guessed), per
    # Ram's instruction not to impose an artificial cap below what the
    # model/provider actually allows.
    "openai/gpt-4o": 16384,
    "openai/o3": 100000,
    "openai/gpt-5": 128000,
    "anthropic/claude-opus-4.6": 128000,
    "anthropic/claude-fable-5": 128000,
    "openai/gpt-5.5": 128000,
    "anthropic/claude-opus-4.8": 128000,
}
# Found empirically: a first real o3 call at 6000 max_tokens returned
# response=None with usage.completion_tokens_details.reasoning_tokens=5952,
# i.e. the whole cap was consumed by hidden reasoning on this large
# (63k-token, binary-format) prompt, leaving zero room for the visible
# answer. Raised the caps well above what "medium" effort should need so a
# real reasoning-heavy pass doesn't get cut off before it can answer.
#
# Second empirical finding, after that first fix: claude-opus-4.6 failed
# 6/6 at max_tokens=8000 with LOW reasoning_tokens (~1000) but
# finish_reason=length -- the VISIBLE answer text itself (round-by-round,
# line-cited work on a 966-line binary trace) is what needs the budget, not
# hidden reasoning. gpt-5 also clipped once at 20000. Raised both past their
# observed usage (opus-4.6 was hitting exactly 8000/8000 every time; gpt-5
# hit 19968/20000 once).
#
# Third finding: opus-4.6 STILL failed at 24000 (hit the cap exactly again,
# reasoning_tokens only 3130 -- so ~20800+ tokens of VISIBLE text alone
# wasn't enough). This model is simply far more verbose per round than the
# others on this prompt. Rather than keep guessing at incremental caps (each
# guess costs a real failed call), pulled each model's REAL
# max_completion_tokens straight from OpenRouter's /models endpoint
# (top_provider.max_completion_tokens) and used that directly -- no
# artificial ceiling below what the provider actually allows.

N_PER_BUCKET_PER_CONDITION = 14  # ~40 total per condition per model, 3 buckets


def load_prompt_template(template_path=None):
    with open(template_path or PROMPT_TEMPLATE_PATH) as f:
        text = f.read()
    start = text.index("```\n") + 4
    end = text.rindex("```")
    return text[start:end]


def build_prompt(trace_text, template_path=None):
    return load_prompt_template(template_path).replace("{trace}", trace_text)


def build_prompt_v2(trace_text):
    """Phase 3 prompt: the short 5-rule + JSON-schema template, wrapped around a
    render_dual() trace. Kept separate from build_prompt() so Phase 1/1b/2 cache
    keys are untouched."""
    return load_prompt_template(PROMPT_TEMPLATE_V2_PATH).replace("{trace}", trace_text)


def cache_key(model, prompt, sample_idx, tag=""):
    h = hashlib.sha256(f"{tag}|{model}|{prompt}|{sample_idx}".encode()).hexdigest()[:24]
    return h


def cache_path(key):
    return os.path.join(CACHE_DIR, f"{key}.json")


def build_dataset(n_rounds=64):
    """All (trace, ground_truth) pairs for the main run. Deterministic given
    fixed seeds, so this is identical across every invocation."""
    items = []
    seed = 0
    for _ in range(N_PER_BUCKET_PER_CONDITION * 3):
        seed += 1
        g = generate_genuine(seed=seed, n_rounds=n_rounds)
        items.append({"kind": "genuine", "trace": g, "bucket": None})
    for bucket in position_buckets(n_rounds):
        for _ in range(N_PER_BUCKET_PER_CONDITION):
            seed += 1
            t = generate_tampered(seed=seed, bucket=bucket, n_rounds=n_rounds)
            items.append({"kind": "tampered", "trace": t, "bucket": bucket})
    return items


def build_small_dataset(n_per_bucket, n_rounds=64, seed_offset=0):
    """A small, deterministic dataset for ablation pilots: n_per_bucket
    genuine + n_per_bucket tampered per bucket (early/middle/late)."""
    items = []
    seed = seed_offset
    for _ in range(n_per_bucket * 3):
        seed += 1
        items.append({"kind": "genuine", "trace": generate_genuine(seed=seed, n_rounds=n_rounds)})
    for bucket in position_buckets(n_rounds):
        for _ in range(n_per_bucket):
            seed += 1
            items.append({"kind": "tampered",
                          "trace": generate_tampered(seed=seed, bucket=bucket, n_rounds=n_rounds)})
    return items


def token_report():
    enc = tiktoken.get_encoding("cl100k_base")
    g64 = generate_genuine(seed=1, n_rounds=64)
    g16 = generate_genuine(seed=1, n_rounds=16)
    print("Prompt token counts (tiktoken cl100k_base), one genuine trace, seed=1:")
    for n_rounds, g in [(64, g64), (16, g16)]:
        for base in ("hex", "binary"):
            trace_text = render_trace(g, base=base, decompose_add=True)
            prompt = build_prompt(trace_text)
            n_tokens = len(enc.encode(prompt))
            print(f"  n_rounds={n_rounds:2d} base={base:6s} -> {n_tokens:6d} tokens")


def dry_run():
    enc = tiktoken.get_encoding("cl100k_base")
    items = build_dataset()
    prompt_lens = []
    for item in items:
        trace_text = render_trace(item["trace"])  # default base=hex, decompose_add=True
        prompt = build_prompt(trace_text)
        prompt_lens.append(len(enc.encode(prompt)))

    n_items = len(items)
    n_models = len(MODELS)
    total_calls = n_items * n_models
    avg_tokens = sum(prompt_lens) / len(prompt_lens)
    total_input_tokens = sum(prompt_lens) * n_models

    print(f"Dataset: {n_items} traces ({N_PER_BUCKET_PER_CONDITION*3} genuine, "
          f"{N_PER_BUCKET_PER_CONDITION*3} tampered across 3 buckets)")
    print(f"Models: {list(MODELS.values())}")
    print(f"Total API calls if run: {total_calls}")
    print(f"Avg prompt tokens (cl100k_base estimate, hex+decompose_add format): {avg_tokens:.0f}")
    print(f"Total input tokens across all calls: {total_input_tokens:,}")
    print()
    token_report()
    print()
    print("Output tokens are now budgeted per model (see COMPLETION_MAX_TOKENS / "
          "REASONING_PARAMS), not a flat 300; real usage will be measured from "
          "actual API responses during --ablate-* / --pilot and reported then.")


def get_api_key():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        return api_key
    env_path = "/home/ram/obsidian/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.strip().split("=", 1)[1]
    print("OPENROUTER_API_KEY not found, aborting.", file=sys.stderr)
    sys.exit(1)


def call_model(model, prompt, api_key, reasoning_params, max_attempts=6, max_tokens_override=None):
    """A malformed/incomplete HTTP response (dropped connection, gateway
    hiccup) is a transport-level failure, not a model judgment -- retried
    with backoff rather than either crashing the whole run or silently
    scoring it as the model's own UNPARSEABLE output. This is the CLAUDE.md
    "robust to parse errors, retry" exception applied one layer below
    parse_response: at the HTTP/JSON layer, before a response even reaches
    scoring."""
    import time as time_module
    import requests
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # max_tokens_override caps the completion budget (Phase 2b: ~32k, well
        # under each model's real ceiling) to force prioritization and prevent
        # budget-exhaustion UNPARSEABLE; default is the model's real max.
        "max_tokens": max_tokens_override if max_tokens_override else COMPLETION_MAX_TOKENS[model],
    }
    if reasoning_params:
        body["reasoning"] = reasoning_params

    last_err = None
    for attempt in range(max_attempts):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
                timeout=900,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            response_text = message["content"]
            # Captured from 2026-07-07 on: the actual hidden-reasoning text
            # (not just its token count), per OpenRouter's reasoning-tokens
            # docs (message.reasoning / message.reasoning_details). Earlier
            # calls (the Phase-1 medium-effort main run) discarded this
            # before it was ever written to cache -- unrecoverable for those.
            reasoning_text = message.get("reasoning")
            reasoning_details = message.get("reasoning_details")
            refusal = message.get("refusal")
            usage = data.get("usage", {})
            finish_reason = choice.get("finish_reason")
            if not response_text:
                reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                if refusal or choice.get("native_finish_reason") == "refusal":
                    print(f"  WARNING: {model} REFUSED (native_finish_reason="
                          f"{choice.get('native_finish_reason')!r}): {refusal!r}", file=sys.stderr)
                    return response_text, reasoning_text, reasoning_details, refusal, usage
                if finish_reason == "error":
                    # Genuine provider-side generation fault (observed on gpt-5.5:
                    # completion_tokens far below max_tokens, cost=0, so nothing
                    # wasted, not a budget-exhaustion case like finish_reason=
                    # "length"). Transient -- retry the same way as a transport
                    # error rather than accepting it as the model's real answer.
                    last_err = RuntimeError(f"provider finish_reason=error, reasoning_tokens={reasoning_tokens}")
                    wait = 5 * (2 ** attempt)
                    print(f"  WARNING: {model} generation error (finish_reason=error, "
                          f"reasoning_tokens={reasoning_tokens}, attempt {attempt + 1}/{max_attempts}) -- "
                          f"retrying in {wait}s.", file=sys.stderr)
                    time_module.sleep(wait)
                    continue
                print(f"  WARNING: empty content from {model} (finish_reason={finish_reason}, "
                      f"reasoning_tokens={reasoning_tokens}, max_tokens={body['max_tokens']}) -- "
                      "likely exhausted the token budget on hidden reasoning.", file=sys.stderr)
            return response_text, reasoning_text, reasoning_details, refusal, usage
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            last_err = e
            wait = 5 * (2 ** attempt)
            print(f"  WARNING: transport error calling {model} (attempt {attempt + 1}/{max_attempts}): "
                  f"{e!r} -- retrying in {wait}s.", file=sys.stderr)
            time_module.sleep(wait)
    print(f"  WARNING: {model} still failing after {max_attempts} attempts ({last_err!r}) -- "
          "giving up, recording as empty/UNPARSEABLE rather than crashing the run.", file=sys.stderr)
    return None, None, None, None, {}


def _call_one(idx, item, model, mode, tag, base, decompose_add, api_key, reasoning_params,
              prompt_template_path=None, max_tokens_override=None):
    """One cache-or-call unit of work, safe to run concurrently (each idx
    writes to a distinct cache file, no shared mutable state).

    prompt_template_path defaults to None (the Phase 1/1b prompt), so every
    existing call site is byte-identical -- passing the Phase 2 scaffold
    template is the only thing that changes the prompt (and therefore the
    cache key)."""
    trace_text = render_trace(item["trace"], base=base, decompose_add=decompose_add)
    prompt = build_prompt(trace_text, template_path=prompt_template_path)
    key = cache_key(model, prompt, idx, tag=tag)
    path = cache_path(key)

    if os.path.exists(path):
        with open(path) as f:
            cached = json.load(f)
        response_text = cached["response"]
        usage = cached.get("usage", {})
    else:
        if mode == "assert-cached":
            raise RuntimeError(f"MISSING CACHE ENTRY for {model} idx={idx} tag={tag}, would call network.")
        response_text, reasoning_text, reasoning_details, refusal, usage = call_model(
            model, prompt, api_key, reasoning_params, max_tokens_override=max_tokens_override)
        with open(path, "w") as f:
            json.dump({"model": model, "prompt_hash": key, "prompt": prompt,
                       "response": response_text, "reasoning": reasoning_text,
                       "reasoning_details": reasoning_details, "refusal": refusal,
                       "usage": usage}, f)

    parsed = parse_response(response_text)
    gt_tampered = item["kind"] == "tampered"
    gt_round = item["trace"].get("tamper_step") if gt_tampered else None
    outcome = score(gt_tampered, gt_round, parsed)
    result = {"model": model, "kind": item["kind"],
              "bucket": item["trace"].get("bucket"), "outcome": outcome}
    return idx, result, usage


# Real per-call wall time varies wildly (o3/gpt-4o: seconds; claude-opus-4.6
# at its true max_completion_tokens: minutes, sometimes tens of minutes) --
# sequential execution of the full 84-trace x 4-model dataset would take
# many hours. IO-bound API calls parallelize safely (each writes a distinct
# cache file), so a thread pool cuts wall time roughly in proportion to
# max_workers with no change in dollar cost.
MAX_WORKERS = 16


def run_items(items, model, mode, tag, base="hex", decompose_add=True, n_rounds=64, api_key=None,
              reasoning_params=None):
    """Concurrent cache-or-call for each item against one model.
    Returns (results list, usage_totals dict)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if reasoning_params is None:
        reasoning_params = REASONING_PARAMS.get(model)
    results = [None] * len(items)
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_call_one, idx, item, model, mode, tag, base, decompose_add, api_key,
                              reasoning_params)
                   for idx, item in enumerate(items)]
        for fut in as_completed(futures):
            idx, result, usage = fut.result()
            results[idx] = result
            for k in usage_totals:
                usage_totals[k] += usage.get(k, 0)
    return results, usage_totals


def summarize(results):
    from collections import Counter
    c = Counter(r["outcome"] for r in results)
    total = len(results)
    print(f"  n={total}  " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    return c


def ablate_format(n_per_bucket, mode="ablate-format"):
    """Real, cheap-model-only: compare hex vs binary at fixed n_rounds=64,
    decompose_add=True (universal). Small n, exploratory, picks a format for
    the main run -- not itself a scored result. mode="assert-cached" makes
    this a genuine no-new-spend reproduce path, same guard run_variant()
    uses for the main/max-effort runs."""
    api_key = get_api_key() if mode != "assert-cached" else None
    items = build_small_dataset(n_per_bucket, n_rounds=64, seed_offset=1000)
    print(f"Ablation A (format): {len(items)} traces x 2 bases on {CHEAP_MODEL}")
    for base in ("hex", "binary"):
        results, usage = run_items(items, CHEAP_MODEL, mode,
                                    tag=f"fmt-{base}", base=base, decompose_add=True,
                                    n_rounds=64, api_key=api_key)
        print(f"base={base}:")
        summarize(results)
        print(f"  usage: prompt_tokens={usage['prompt_tokens']:,} "
              f"completion_tokens={usage['completion_tokens']:,}")


def ablate_length(n_per_bucket, base, mode="ablate-length"):
    """Real, cheap-model-only: compare full 64-round vs reduced 16-round at
    a fixed (already-chosen) base. Tests whether trace length alone changes
    detection accuracy. mode="assert-cached" makes this a genuine
    no-new-spend reproduce path, same guard run_variant() uses."""
    api_key = get_api_key() if mode != "assert-cached" else None
    for n_rounds in (64, 16):
        items = build_small_dataset(n_per_bucket, n_rounds=n_rounds, seed_offset=2000)
        results, usage = run_items(items, CHEAP_MODEL, mode,
                                    tag=f"len-{n_rounds}-{base}", base=base, decompose_add=True,
                                    n_rounds=n_rounds, api_key=api_key)
        print(f"n_rounds={n_rounds} (base={base}):")
        summarize(results)
        print(f"  usage: prompt_tokens={usage['prompt_tokens']:,} "
              f"completion_tokens={usage['completion_tokens']:,}")


def run_variant(mode, models, reasoning_params_by_model, tag_prefix, results_filename,
                 n_pilot=10, base="hex", n_rounds=64, prompt_template_path=None,
                 pilot_indices=None, max_tokens_override=None):
    """Runs all (tier, item) pairs across every model in `models` in ONE
    shared thread pool, rather than one model at a time. This matters
    because claude-opus-4.6/claude-fable-5 completions can take many
    minutes each while the fast models finish in seconds -- running models
    sequentially would make the whole job wait on the slow ones repeatedly.
    Interleaving means fast models' results land early while slow calls
    churn in the background. `tag_prefix` and `results_filename` are
    per-variant so a max-effort run never collides with (or overwrites) the
    medium-effort Phase 1 cache/results."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    os.makedirs(CACHE_DIR, exist_ok=True)
    api_key = get_api_key() if mode != "assert-cached" else None
    # Carry the TRUE dataset index alongside each item so a pilot subset uses
    # the same cache key as the live run for the same trace (idx is part of the
    # cache key). Otherwise a pilot on a re-indexed subset would cache under
    # idx=0,1,2... and the live run would have to re-call those same traces.
    indexed_items = list(enumerate(build_dataset(n_rounds=n_rounds)))
    if mode == "pilot":
        # Default pilot slice is the first n_pilot items (all genuine, since
        # build_dataset orders genuine first) -- fine as a pure cost probe.
        # pilot_indices lets a caller pick a MIXED genuine+tampered slice so the
        # pilot also yields a detection signal, not just false-positive behavior.
        if pilot_indices is not None:
            indexed_items = [indexed_items[i] for i in pilot_indices]
        else:
            indexed_items = indexed_items[:n_pilot]

    all_results = []
    usage_by_tier = {tier: {"prompt_tokens": 0, "completion_tokens": 0} for tier in models}
    tag = f"{tag_prefix}-{base}-{n_rounds}"
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {}
        # Submit round-robin across models (one task per model per round),
        # NOT all of one model then the next: ThreadPoolExecutor's queue is
        # FIFO, so a block submission order would dispatch all fast-model
        # tasks before a single slow-model task ever gets a worker, defeating
        # the whole point of sharing one pool.
        for idx, item in indexed_items:
            for tier, model in models.items():
                fut = ex.submit(_call_one, idx, item, model, mode, tag, base, True, api_key,
                                 reasoning_params_by_model.get(model), prompt_template_path,
                                 max_tokens_override)
                futures[fut] = tier
        for fut in as_completed(futures):
            tier = futures[fut]
            idx, result, usage = fut.result()
            result["tier"] = tier
            all_results.append(result)
            for k in usage_by_tier[tier]:
                usage_by_tier[tier][k] += usage.get(k, 0)

    for tier, model in models.items():
        tier_results = [r for r in all_results if r["tier"] == tier]
        print(f"{tier} ({model}):")
        summarize(tier_results)
        u = usage_by_tier[tier]
        print(f"  usage: prompt_tokens={u['prompt_tokens']:,} completion_tokens={u['completion_tokens']:,}")

    # A "pilot" mode run must never overwrite the authoritative "live" results
    # file (this happened for real: an opus-4.8 pilot silently clobbered
    # results_maxeffort.jsonl's 420-row live result down to 56 rows; recovered
    # via --assert-cached-max-effort, since the underlying cache was untouched,
    # but the file-naming bug that allowed it is fixed here, not just patched
    # around). "live" and "assert-cached" both write to the canonical name
    # (assert-cached SHOULD reproduce it byte-identical -- that's the point of
    # the check); only "pilot" gets diverted to its own filename.
    if mode == "pilot":
        base_name, ext = os.path.splitext(results_filename)
        results_filename = f"{base_name}_pilot{ext}"
    results_path = os.path.join(os.path.dirname(__file__), results_filename)
    with open(results_path, "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(all_results)} results to {results_path}")


def run_main(mode, n_pilot=10, base="hex", n_rounds=64):
    """Phase 1: the original 4 models, medium reasoning effort. Unchanged
    behavior/cache tag from the completed live run (tag 'main-...',
    results.jsonl) -- a rerun still reproduces the exact Phase 1 result with
    zero new API calls."""
    run_variant(mode, MODELS, REASONING_PARAMS, "main", "results.jsonl",
                n_pilot=n_pilot, base=base, n_rounds=n_rounds)


def run_max_effort(mode, n_pilot=10, base="binary", n_rounds=64, models=None):
    """Max-effort re-run (2026-07-07): the original 4 models plus
    claude-fable-5 and gpt-5.5 (Epoch Capability Index top models, per Ram),
    all at effort:'max' where a reasoning channel exists. Separate tag
    ('maxeffort-...') and results file so this never collides with or
    overwrites the medium-effort Phase 1 results -- both are kept for
    comparison. `models` defaults to ALL_MODELS (pilot, includes
    claude-fable-5); the live run passes LIVE_MAX_EFFORT_MODELS (fable-5
    dropped -- 100% refusal in the pilot, zero usable data per dollar)."""
    if models is None:
        models = ALL_MODELS
    run_variant(mode, models, MAX_EFFORT_REASONING_PARAMS, "maxeffort",
                "results_maxeffort.jsonl", n_pilot=n_pilot, base=base, n_rounds=n_rounds)


# Phase 2 (verification scaffold). Full run targets ONLY the two models that
# showed nonzero right-for-right-reason detection in Phase 1b: claude-opus-4.6
# (8/42) and gpt-5.5 (5/42). The other Phase 1b models were 0/42, so there is
# no detection for a scaffold to improve on -- spending on them would only
# re-measure zero. Same effort settings as Phase 1b (MAX_EFFORT_REASONING_PARAMS)
# and same binary base, so the ONLY variable vs Phase 1b is the scaffold prompt.
PHASE2_MODELS = {
    "horizon_719min": "anthropic/claude-opus-4.6",
    "eci_159_gpt55": "openai/gpt-5.5",
}
# The pilot uses ONE model to save money (opus-4.6 alone runs ~$3/call). Default
# to gpt-5.5: it is the cheaper of the two nonzero detectors (~$1.5/call vs ~$3),
# so more pilot calls fit under a tight budget, and unlike opus-4.6 (already
# saturating its ~107k/128k output cap in Phase 1b, so its cost is already
# characterized and near-fixed) gpt-5.5 has output headroom the longer scaffold
# will actually use -- so a real phase-2 gpt-5.5 cost point is the higher-value
# measurement. Override with --phase2-pilot-model.
PHASE2_PILOT_MODELS = {"eci_159_gpt55": "openai/gpt-5.5"}

# A mixed genuine+tampered pilot slice (dataset indices), so the pilot yields a
# real detection signal, not just false-positive behavior on all-genuine traces.
# build_dataset order: 0-41 genuine, 42-55 tampered-early, 56-69 tampered-middle,
# 70-83 tampered-late. This picks 2 genuine + one from each tamper bucket, then
# more genuine/tampered, so any prefix of length N stays balanced.
PHASE2_PILOT_INDICES = [0, 42, 56, 70, 1, 43, 57, 71, 2, 58]


def run_phase2(mode, n_pilot=8, base="binary", n_rounds=64, models=None,
               pilot_model_key=None):
    """Phase 2: the verification-scaffold variant. Same 84 traces, same binary
    rendering, same max-effort settings, same r4r scoring as Phase 1b -- the
    ONLY change is the scaffold prompt (prompt_template_phase2.md). Separate
    cache tag ('phase2-...') and results file (results_phase2.jsonl) so it never
    collides with Phase 1 (results.jsonl) or Phase 1b (results_maxeffort.jsonl)."""
    if models is None:
        if mode == "pilot":
            models = PHASE2_PILOT_MODELS
            if pilot_model_key:
                models = {pilot_model_key: PHASE2_MODELS[pilot_model_key]}
        else:
            models = PHASE2_MODELS
    pilot_indices = PHASE2_PILOT_INDICES[:n_pilot] if mode == "pilot" else None
    run_variant(mode, models, MAX_EFFORT_REASONING_PARAMS, "phase2",
                "results_phase2.jsonl", n_pilot=n_pilot, base=base, n_rounds=n_rounds,
                prompt_template_path=PHASE2_PROMPT_TEMPLATE_PATH,
                pilot_indices=pilot_indices)


# Phase 2b (bounded scaffold). Same two target models as Phase 2. Pilot uses a
# mixed genuine+tampered slice across both models (the coordinator wants both
# piloted, unlike Phase 2's single-model cost probe).
PHASE2B_MODELS = {
    "horizon_719min": "anthropic/claude-opus-4.6",
    "eci_159_gpt55": "openai/gpt-5.5",
}
# 6 mixed indices: 1 genuine + tampered early/early/middle/middle/late, so the
# pilot exercises false-positive behavior AND detection across all 3 buckets.
# (build_dataset order: 0-41 genuine, 42-55 early, 56-69 middle, 70-83 late.)
PHASE2B_PILOT_INDICES = [0, 42, 43, 56, 57, 70]


def run_phase2b(mode, n_pilot=6, base="binary", n_rounds=64, models=None,
                max_tokens=None):
    """Phase 2b: the BOUNDED verification-scaffold variant. Same 84 traces, same
    binary base, same max-effort reasoning as Phase 1b/2, but a two-pass prompt
    (triage <=5 rounds, carry-chain only those) and a CAPPED output budget
    (max_tokens, default PHASE2B_MAX_TOKENS ~32k) so opus can't drown. Distinct
    cache tag ('phase2b-...') and results file ('results_phase2b.jsonl')."""
    if models is None:
        models = PHASE2B_MODELS
    if max_tokens is None:
        max_tokens = PHASE2B_MAX_TOKENS
    pilot_indices = PHASE2B_PILOT_INDICES[:n_pilot] if mode == "pilot" else None
    run_variant(mode, models, MAX_EFFORT_REASONING_PARAMS, "phase2b",
                "results_phase2b.jsonl", n_pilot=n_pilot, base=base, n_rounds=n_rounds,
                prompt_template_path=PHASE2B_PROMPT_TEMPLATE_PATH,
                pilot_indices=pilot_indices, max_tokens_override=max_tokens)


if __name__ == "__main__":
    os.makedirs(CACHE_DIR, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ablate-format", type=int, nargs="?", const=2)
    parser.add_argument("--ablate-length", type=int, nargs="?", const=2)
    parser.add_argument("--base", default="hex", choices=["hex", "binary"])
    parser.add_argument("--pilot", type=int, nargs="?", const=10)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--assert-cached", action="store_true")
    parser.add_argument("--pilot-max-effort", type=int, nargs="?", const=8,
                         help="Pilot the max-effort variant (original 4 + claude-fable-5 + "
                              "gpt-5.5, effort='max') on N traces, separate cache tag/results "
                              "file from the medium-effort Phase 1 run.")
    parser.add_argument("--live-max-effort", action="store_true")
    parser.add_argument("--assert-cached-max-effort", action="store_true")
    parser.add_argument("--phase2", action="store_true",
                         help="Verification-scaffold variant. Composes with --pilot N / "
                              "--live / --assert-cached: e.g. `--phase2 --pilot 6`, "
                              "`--phase2 --live`, `--phase2 --assert-cached`. Same 84 traces, "
                              "same binary base, same max-effort settings as the max-effort "
                              "run; only the prompt changes (prompt_template_phase2.md).")
    parser.add_argument("--phase2-pilot-model", default=None,
                         help="For --phase2 --pilot, which single model to pilot "
                              "(model key, e.g. 'horizon_719min' for opus-4.6 or "
                              "'eci_159_gpt55' for gpt-5.5). Default: gpt-5.5 (cheaper).")
    parser.add_argument("--phase2b", action="store_true",
                         help="BOUNDED verification-scaffold variant (two-pass, capped "
                              "output). Composes with --pilot N / --live / --assert-cached, "
                              "same as --phase2. Targets opus-4.6 + gpt-5.5.")
    parser.add_argument("--phase2b-max-tokens", type=int, default=None,
                         help="Output-token cap for --phase2b calls (default "
                              f"{PHASE2B_MAX_TOKENS}). Part of the affordance, not the cache "
                              "key -- keep it fixed across a pilot and its matching live run.")
    args = parser.parse_args()

    if args.phase2b:
        # --phase2b modifier: action from --pilot / --live / --assert-cached.
        base = args.base if args.base != "hex" else "binary"  # phase 2b baseline is binary
        mt = args.phase2b_max_tokens  # None -> run_phase2b uses PHASE2B_MAX_TOKENS
        if args.assert_cached:
            run_phase2b("assert-cached", base=base, max_tokens=mt)
        elif args.live:
            run_phase2b("live", base=base, max_tokens=mt)
        elif args.pilot:
            run_phase2b("pilot", n_pilot=args.pilot, base=base, max_tokens=mt)
        else:
            print("--phase2b needs one of --pilot N, --live, or --assert-cached.", file=sys.stderr)
            sys.exit(2)
    elif args.phase2:
        # --phase2 is a modifier: the action comes from --pilot / --live /
        # --assert-cached, routed to the scaffold variant instead of Phase 1.
        base = args.base if args.base != "hex" else "binary"  # phase 2 baseline is binary
        if args.assert_cached:
            run_phase2("assert-cached", base=base)
        elif args.live:
            run_phase2("live", base=base)
        elif args.pilot:
            run_phase2("pilot", n_pilot=args.pilot, base=base,
                       pilot_model_key=args.phase2_pilot_model)
        else:
            print("--phase2 needs one of --pilot N, --live, or --assert-cached.", file=sys.stderr)
            sys.exit(2)
    elif args.dry_run:
        dry_run()
    elif args.ablate_format:
        ablate_format(args.ablate_format, mode="assert-cached" if args.assert_cached else "ablate-format")
    elif args.ablate_length:
        ablate_length(args.ablate_length, base=args.base,
                       mode="assert-cached" if args.assert_cached else "ablate-length")
    elif args.pilot:
        run_main("pilot", n_pilot=args.pilot, base=args.base)
    elif args.live:
        run_main("live", base=args.base)
    elif args.assert_cached:
        run_main("assert-cached", base=args.base)
    elif args.pilot_max_effort:
        run_max_effort("pilot", n_pilot=args.pilot_max_effort, base=args.base)
    elif args.live_max_effort:
        run_max_effort("live", base=args.base, models=LIVE_MAX_EFFORT_MODELS)
    elif args.assert_cached_max_effort:
        run_max_effort("assert-cached", base=args.base, models=LIVE_MAX_EFFORT_MODELS)
    else:
        print(__doc__)
