"""Phase 3 Inspect (inspect_ai) task: maximally-observable SHA-256 tamper
verification (redesign-proposal.md).

Every lever is a `-T` task parameter, nothing hardcoded:
  model_key, renderer (dual|binary), prompt_variant (v2), reasoning_effort,
  max_tokens, n_per_bucket. The same 84 seeded traces as every prior phase.

Reproducibility (per the reproducibility-and-evidence skill + Ram's directive):
  - Native Inspect caching (cache=True) on the generate call -> a rerun is a
    FREE replay (zero new API calls) as long as model/prompt/config are
    unchanged. This is Phase 3's equivalent of the older --assert-cached.
  - .eval logs in logs_inspect_v2/ capture the full prompt, full visible output,
    and ContentReasoning blocks natively.
  - The scorer stores, per sample, the full parsed JSON + every metric input +
    provenance (model_key, ECI, effort, max_tokens, renderer, seed, git commit,
    exact model id as returned by the API) so results_v2.jsonl and all headline
    numbers are recomputable offline from the logs with zero new calls.

Reproduce (one model per invocation; see README.md Reproduce block for the full
set with every -T parameter):
    inspect eval inspect_task_v2.py --model openrouter/openai/gpt-4o \
        -T model_key=openai/gpt-4o -T renderer=dual --log-dir logs_inspect_v2
"""

import json
import subprocess

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, MemoryDataset
from inspect_ai.model import GenerateConfig
from inspect_ai.model._cache import CachePolicy
from inspect_ai.scorer import scorer, Score, Target, CORRECT, INCORRECT, accuracy, stderr
from inspect_ai.solver import TaskState, generate

from run_experiment import (
    build_dataset,
    build_prompt_v2,
    MAX_EFFORT_REASONING_PARAMS,
    COMPLETION_MAX_TOKENS,
    ECI_SCORES,
    ECI_SNAPSHOT_DATE,
)
from sha256_trace import render_dual, render_trace, position_buckets, \
    generate_genuine, generate_tampered
from score_v2 import (
    parse_response_v2, score_v2, is_strict_mechanism,
    true_and_printed_sums, arithmetic_error_stats, verdict_evidence_consistent,
)


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "-C", __file__.rsplit("/", 1)[0], "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


GIT_COMMIT = _git_commit()


def _render(item, renderer):
    if renderer == "dual":
        return render_dual(item["trace"])
    if renderer == "binary":
        # Arm B attribution control: OLD binary-only rendering, NEW v2 prompt+schema.
        return render_trace(item["trace"], base="binary", decompose_add=True)
    raise ValueError(f"unknown renderer {renderer!r}")


def _make_sample(idx, item, renderer):
    trace_text = _render(item, renderer)
    prompt = build_prompt_v2(trace_text)
    is_tampered = item["kind"] == "tampered"
    tamper_round = item["trace"].get("tamper_step") if is_tampered else None
    true_sums, printed_sums = true_and_printed_sums(item["trace"]["rounds"])
    n = item["trace"]["n_rounds"]
    # store sums as round-indexed lists (JSON-friendly; rounds are 0..n-1)
    target = json.dumps({"is_tampered": is_tampered, "tamper_round": tamper_round})
    return Sample(
        input=prompt,
        target=target,
        id=idx,
        metadata={
            "kind": item["kind"],
            "bucket": item["trace"].get("bucket"),
            "tamper_round": tamper_round,
            "seed": idx + 1,  # build_dataset() seeds genuine 1..42 then tampered 43..84
            "true_sums": [true_sums[t] for t in range(n)],
            "printed_sums": [printed_sums[t] for t in range(n)],
        },
    )


@scorer(metrics=[accuracy(), stderr()])
def r4r_v2_scorer(model_key: str, renderer: str, reasoning_effort: str, max_tokens: int):
    """Mechanism-aware r4r (score.py rule, unchanged) plus the full Phase 3
    metric inputs and provenance, all stored in Score.metadata so every headline
    number is recomputable offline from the .eval log with zero new API calls."""

    async def do_score(state: TaskState, target: Target) -> Score:
        gt = json.loads(target.text)
        text = state.output.completion
        parsed = parse_response_v2(text)
        outcome = score_v2(gt["is_tampered"], gt["tamper_round"], parsed)

        # rebuild round-indexed true/printed sums from sample metadata
        true_list = state.metadata["true_sums"]
        printed_list = state.metadata["printed_sums"]
        true_sums = {t: d for t, d in enumerate(true_list)}
        printed_sums = {t: d for t, d in enumerate(printed_list)}
        n_rep, n_err, n_copy = arithmetic_error_stats(parsed["json"], true_sums, printed_sums)

        # exact model id/version as the API returned it (provenance)
        api_model = getattr(state.output, "model", None) or model_key

        correct = outcome in ("TN", "TP_r4r")
        return Score(
            value=CORRECT if correct else INCORRECT,
            answer=f"verdict={parsed['verdict']} round={parsed['claimed_round']} p={parsed['p_tampered']}",
            explanation=outcome,
            metadata={
                "outcome": outcome,
                "verdict": parsed["verdict"],
                "claimed_round": parsed["claimed_round"],
                "verdict_source": parsed["verdict_source"],
                "p_tampered": parsed["p_tampered"],
                "p_source": parsed["p_source"],
                "p_malformed": parsed["p_malformed"],
                "json_present": parsed["json"] is not None,
                "json_tamper_eq": parsed["json_tamper_eq"],
                "disagreement": parsed["disagreement"],
                "strict_mechanism": is_strict_mechanism(outcome, parsed),
                "verdict_evidence_consistent": verdict_evidence_consistent(parsed, outcome),
                "arith_n_reported": n_rep,
                "arith_n_error": n_err,
                "arith_n_copy": n_copy,
                # provenance
                "kind": state.metadata["kind"],
                "bucket": state.metadata["bucket"],
                "tamper_round": state.metadata["tamper_round"],
                "seed": state.metadata["seed"],
                "model_key": model_key,
                "api_model": api_model,
                "eci": ECI_SCORES[model_key],
                "eci_snapshot_date": ECI_SNAPSHOT_DATE,
                "reasoning_effort": reasoning_effort,
                "max_tokens": max_tokens,
                "renderer": renderer,
                "git_commit": GIT_COMMIT,
            },
        )

    return do_score


def _pilot_slice(pilot_n):
    """First pilot_n indices from a fixed interleaving (genuine, early, middle,
    late, genuine, ...), so any prefix is balanced and includes a late tamper
    early. Returns (true_dataset_index, item) pairs (same seeds/cache as full)."""
    full = build_dataset()  # 0-41 genuine, 42-55 early, 56-69 mid, 70-83 late
    gen = list(range(0, 42))
    early = list(range(42, 56))
    mid = list(range(56, 70))
    late = list(range(70, 84))
    order = []
    for k in range(14):
        for lst in (gen, early, mid, late):
            if k < len(lst):
                order.append(lst[k])
    chosen = order[:pilot_n]
    return [(i, full[i]) for i in chosen]


def _balanced_slice(balanced_n):
    """balanced_n//2 genuine + balanced_n//2 tampered (tampered round-robin across
    early/middle/late), a paired SUBSET of the 84. Used for Arm B (attribution
    control): same traces, OLD binary rendering vs Arm A's dual."""
    full = build_dataset()
    half = balanced_n // 2
    genuine = list(range(0, half))
    early, mid, late = list(range(42, 56)), list(range(56, 70)), list(range(70, 84))
    tampered = []
    k = 0
    while len(tampered) < half:
        for lst in (early, mid, late):
            if len(tampered) < half and k < len(lst):
                tampered.append(lst[k])
        k += 1
    chosen = genuine + tampered
    return [(i, full[i]) for i in chosen]


@task
def sha256_tamper_v2(model_key: str, renderer: str = "dual", prompt_variant: str = "v2",
                     reasoning_effort: str = None, max_tokens: int = None,
                     n_per_bucket: int = 14, pilot_n: int = None, balanced_n: int = None,
                     sample_ids: str = None, resample_tag: str = None):
    """Phase 3 task. All levers are -T parameters.

    model_key      : org/model, selects effort/cap defaults + ECI (crash-loud if unknown)
    renderer       : 'dual' (Phase 3) or 'binary' (Arm B attribution control)
    prompt_variant : 'v2' (only variant; kept as an explicit lever)
    reasoning_effort / max_tokens : override the per-model defaults if given
    n_per_bucket   : 14 => full N=84; smaller for pilots (mixed slice below)
    sample_ids     : comma-separated true dataset indices (0-83) to run, e.g.
                      "0,5,10,11,20,28". Targets an exact subset (e.g. specific
                      UNPARSEABLE completion-run samples) instead of a slice.
    resample_tag   : when set, busts Inspect's native cache (CachePolicy.scopes)
                      so a byte-identical (model, prompt, config) rerun makes a
                      genuinely NEW API call instead of replaying the cached
                      result for free. Needed when max_tokens is already at the
                      provider's real ceiling (no config field left to change)
                      and you still want a fresh stochastic resample.
    """
    if model_key not in MAX_EFFORT_REASONING_PARAMS:
        raise ValueError(f"unknown model_key {model_key!r}, not in MAX_EFFORT_REASONING_PARAMS")
    if prompt_variant != "v2":
        raise ValueError(f"unknown prompt_variant {prompt_variant!r}")

    # per-model defaults (max effort), overridable by -T
    default_params = MAX_EFFORT_REASONING_PARAMS[model_key] or {}
    effort = reasoning_effort if reasoning_effort is not None else default_params.get("effort")
    cap = max_tokens if max_tokens is not None else COMPLETION_MAX_TOKENS[model_key]

    config = GenerateConfig(max_tokens=cap)
    if effort:
        config.reasoning_effort = effort

    if sample_ids is not None:
        # Inspect's -T CLI parser auto-splits a comma-separated value into a
        # list before it reaches here, so this arrives as either a str
        # ("0,5,10") from a direct Python call or a list ([0, 5, 10]) from
        # `inspect eval ... -T sample_ids=0,5,10`.
        ids = [int(x) for x in sample_ids.split(",")] if isinstance(sample_ids, str) else [int(x) for x in sample_ids]
        full = build_dataset()
        indexed = [(i, full[i]) for i in ids]
    elif balanced_n is not None:
        indexed = _balanced_slice(balanced_n)  # Arm B: 50/50 genuine/tampered subset
    elif pilot_n is not None:
        indexed = _pilot_slice(pilot_n)  # exact-count mixed slice
    elif n_per_bucket != 14:
        indexed = _pilot_items(n_per_bucket)  # legacy bucket-based mixed slice
    else:
        indexed = list(enumerate(build_dataset()))  # canonical 84

    dataset = MemoryDataset([_make_sample(idx, item, renderer) for idx, item in indexed])

    cache = CachePolicy(scopes={"resample_tag": resample_tag}) if resample_tag else True
    return Task(
        dataset=dataset,
        solver=[generate(cache=cache)],  # native Inspect cache -> free replay (unless busted)
        scorer=r4r_v2_scorer(model_key, renderer, effort or "none", cap),
        config=config,
    )


def _pilot_items(n_per_bucket):
    """A small MIXED (genuine + early/middle/late tampered) slice for pilots,
    returned as (true_dataset_index, item) pairs so cache keys and provenance
    match the full run's for the same trace. Deterministic (same seeds)."""
    full = build_dataset()
    # full ordering: 0-41 genuine (seeds 1-42), then 14 early / 14 middle / 14 late
    genuine_idx = list(range(0, n_per_bucket))
    early = list(range(42, 42 + n_per_bucket))
    middle = list(range(56, 56 + n_per_bucket))
    late = list(range(70, 70 + n_per_bucket))
    chosen = genuine_idx + early + middle + late
    return [(i, full[i]) for i in chosen]


if __name__ == "__main__":
    # zero-API dry check: build the task for a model and print sample/token info
    import sys
    mk = sys.argv[1] if len(sys.argv) > 1 else "openai/gpt-4o"
    t = sha256_tamper_v2(model_key=mk)
    print(f"task built for {mk}: {len(t.dataset)} samples, renderer=dual, "
          f"cache=on, config={t.config}")
