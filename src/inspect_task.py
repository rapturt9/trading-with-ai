"""Inspect AI (inspect_ai) port of the SHA-256 tamper-detection eval.

Same dataset, prompt, and scoring rule as the max-effort live run in
run_experiment.py (84 traces: 42 genuine + 42 tampered across
early/middle/late buckets, n_rounds=64, base="binary") -- reuses
build_dataset()/build_prompt()/render_trace() and score.py's
parse_response()/score() directly rather than reimplementing them.

Unlike run_experiment.py's custom OpenRouter request loop, this produces
real .eval log files (viewable with `inspect view`) that capture the full
input, full response, and full reasoning content natively per sample, no
separate cache-file bookkeeping needed.

Per-model reasoning-effort and max-tokens settings are read from
MAX_EFFORT_REASONING_PARAMS / COMPLETION_MAX_TOKENS in run_experiment.py
(the same empirically-confirmed values used for the live run), selected via
the `model_key` task parameter -- so there is one source of truth for those
settings, not a duplicated copy.

Reproduce (one model at a time, each needs its own reasoning_effort/max_tokens):
    inspect eval src/inspect_task.py --model openrouter/openai/gpt-4o -T model_key=openai/gpt-4o
    inspect eval src/inspect_task.py --model openrouter/openai/o3 -T model_key=openai/o3
    inspect eval src/inspect_task.py --model openrouter/openai/gpt-5 -T model_key=openai/gpt-5
    inspect eval src/inspect_task.py --model openrouter/anthropic/claude-opus-4.6 -T model_key=anthropic/claude-opus-4.6
    inspect eval src/inspect_task.py --model openrouter/openai/gpt-5.5 -T model_key=openai/gpt-5.5

View results: inspect view --log-dir data/logs_raw
"""

import json

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, MemoryDataset
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import scorer, Score, Target, CORRECT, INCORRECT, accuracy, stderr
from inspect_ai.solver import TaskState, generate

from run_experiment import (
    build_dataset,
    build_prompt,
    MAX_EFFORT_REASONING_PARAMS,
    COMPLETION_MAX_TOKENS,
)
from sha256_trace import render_trace
from score import parse_response, score as score_response

BASE = "binary"  # matches run_max_effort's default, same as the live run


def _make_sample(idx, item):
    trace_text = render_trace(item["trace"], base=BASE, decompose_add=True)
    prompt = build_prompt(trace_text)
    is_tampered = item["kind"] == "tampered"
    tamper_round = item["trace"].get("tamper_step") if is_tampered else None
    target = json.dumps({"is_tampered": is_tampered, "tamper_round": tamper_round})
    return Sample(
        input=prompt,
        target=target,
        id=idx,
        metadata={
            "kind": item["kind"],
            "bucket": item["trace"].get("bucket"),
            "tamper_round": tamper_round,
        },
    )


@scorer(metrics=[accuracy(), stderr()])
def r4r_scorer():
    """Right-for-right-reason scoring, reusing score.py's parse_response()/
    score() so the rule is identical to every other phase of this project.
    Score.value is CORRECT only for TN and TP_r4r (the two "the model got
    this exactly right" outcomes); the full 6-way category (TN/TP_r4r/
    TP_wrong_round/FP/FN/UNPARSEABLE) is preserved in metadata so the
    project's real headline metric -- TP_r4r rate among tampered traces --
    can be recomputed exactly via summarize_inspect_logs.py."""

    async def do_score(state: TaskState, target: Target) -> Score:
        gt = json.loads(target.text)
        parsed = parse_response(state.output.completion)
        outcome = score_response(gt["is_tampered"], gt["tamper_round"], parsed)
        correct = outcome in ("TN", "TP_r4r")
        return Score(
            value=CORRECT if correct else INCORRECT,
            answer=f"verdict={parsed['verdict']} round={parsed['claimed_round']}",
            explanation=outcome,
            metadata={"outcome": outcome, **state.metadata},
        )

    return do_score


@task
def sha256_tamper_detection(model_key: str):
    """model_key selects the reasoning_effort/max_tokens config from
    run_experiment.py's MAX_EFFORT_REASONING_PARAMS/COMPLETION_MAX_TOKENS --
    must match the org/model part of the --model openrouter/<model_key> used
    to invoke this task, e.g. model_key=anthropic/claude-opus-4.6."""
    if model_key not in MAX_EFFORT_REASONING_PARAMS:
        raise ValueError(f"unknown model_key {model_key!r}, not in MAX_EFFORT_REASONING_PARAMS")

    reasoning_params = MAX_EFFORT_REASONING_PARAMS[model_key] or {}
    max_tokens = COMPLETION_MAX_TOKENS[model_key]

    config = GenerateConfig(max_tokens=max_tokens)
    if "effort" in reasoning_params:
        config.reasoning_effort = reasoning_params["effort"]
    if "max_tokens" in reasoning_params:
        # anthropic explicit reasoning-token-budget style (Phase 1 only;
        # unused by MAX_EFFORT_REASONING_PARAMS, kept for parity with
        # run_experiment.py's REASONING_PARAMS shape)
        config.reasoning_tokens = reasoning_params["max_tokens"]

    items = build_dataset()
    dataset = MemoryDataset([_make_sample(idx, item) for idx, item in enumerate(items)])

    return Task(
        dataset=dataset,
        solver=[generate()],
        scorer=r4r_scorer(),
        config=config,
    )
