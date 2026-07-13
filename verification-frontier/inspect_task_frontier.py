"""N50 ops-horizon Inspect (inspect_ai) task: SHA multi-block and small-curve
ECDSA tamper-verification, parameterized so family/rung/n/seed/model are all
`-T` task parameters, following ../src/inspect_task_checkable.py's
pattern (Inspect Task, MemoryDataset, native caching, a scorer that stores
full provenance in Score.metadata so every headline number is recomputable
offline from the .eval log with zero new API calls).

Reasoning-effort/max-tokens defaults and ECI values are IMPORTED from
../src/run_experiment.py (MAX_EFFORT_REASONING_PARAMS,
COMPLETION_MAX_TOKENS, ECI_SCORES), not copied -- this experiment reuses the
same five live-run models and the same empirically-confirmed per-provider
"real max effort" values that file already established.

Reproduce (one model/family/rung per invocation; see README.md's Reproduce
block for the full pilot set):
    inspect eval inspect_task_frontier.py --model openrouter/anthropic/claude-opus-4.6 \
        -T family=sha -T model_key=anthropic/claude-opus-4.6 -T rung=1 -T n=20 \
        --log-dir logs_pilot
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, MemoryDataset
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import scorer, Score, Target, CORRECT, INCORRECT, accuracy, stderr
from inspect_ai.solver import TaskState, generate

import sha256_multiblock as shamb
import sha256_tamper_classes as shatc
import ecdsa_trace as ecdsa
import p256_trace as p256
import report_payload
from score_frontier import parse_response_frontier, score_frontier

from run_experiment import MAX_EFFORT_REASONING_PARAMS, COMPLETION_MAX_TOKENS, ECI_SCORES  # noqa: E402


def _git_commit():
    # timeout=5: this vault has an autosync cron that periodically runs git
    # commit/merge against this same repo (see CLAUDE.md's vault map), which
    # can transiently lock .git while this subprocess call (run at IMPORT
    # TIME, i.e. before inspect's own task-discovery timeout) is blocked
    # waiting on it -- observed as concurrent `inspect eval` launches
    # intermittently failing with a misleading "No inspect tasks were found"
    # (task-discovery timing out on a slow import, not a real missing task).
    # A bounded timeout turns a hang into a fast, caught exception instead.
    try:
        return subprocess.check_output(
            ["git", "-C", os.path.dirname(__file__), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except Exception:
        return "unknown"


GIT_COMMIT = _git_commit()

# Closed set the installed inspect_ai's GenerateConfig.reasoning_effort actually
# accepts (checked empirically, see the extra_body workaround below for "max").
_VALID_REASONING_EFFORT_LITERALS = {"none", "minimal", "low", "medium", "high", "xhigh"}

SHA_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt_template_frontier_sha.md")
ECDSA_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt_template_frontier_ecdsa.md")
P256_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt_template_frontier_p256.md")

RECHECK_REMINDER = (" Before moving to the next line, explicitly recompute this "
                     "line's value from its printed inputs and confirm it matches "
                     "before treating it as settled ground truth for any later line.")

SHA_RENDERING_KWARGS = {
    "dual": dict(binary_bitops=True, binary_new=True, decimal_additions=True, binary_state=True),
    "decimal_densified": dict(binary_bitops=False, binary_new=False, decimal_additions=True, binary_state=False),
}


def _load_template(path):
    with open(path) as f:
        text = f.read()
    start = text.index("```\n") + 4
    end = text.rindex("```")
    return text[start:end]


def build_prompt_sha(trace_text):
    return _load_template(SHA_PROMPT_PATH).replace("{trace}", trace_text)


def build_prompt_ecdsa(trace_text, prompt_variant="base"):
    reminder = RECHECK_REMINDER if prompt_variant == "recheck_reminder" else ""
    return (_load_template(ECDSA_PROMPT_PATH)
            .replace("{recheck_reminder}", reminder)
            .replace("{trace}", trace_text))


def build_prompt_p256(trace_text):
    return _load_template(P256_PROMPT_PATH).replace("{trace}", trace_text)


# --------------------------------------------------------------------------
# SHA multi-block dataset
# --------------------------------------------------------------------------

SHA_TAMPER_CLASSES = ("addition", "bitwise", "schedule_word")
BUCKETS = ("early", "middle", "late")


def build_sha_dataset(n_blocks, n, seed_start=1, payload="random"):
    """n total: n//2 genuine + remainder tampered. payload="random" (default):
    tampered round-robin across the 3 tamper classes x 3 position buckets (9
    combos), so a small n still samples every class at least once when
    n >= 18. payload="report": uses report_payload.py's attestation-report-
    shaped message instead of random bytes, via ../plan.md's TEE-realism
    item 1 -- only the "addition" tamper class is wired for report-shaped
    payloads (report_payload.py's generate_tampered only overrides
    sha256_multiblock's addition-class generator, not sha256_tamper_classes'
    bitwise/schedule_word ones), so payload="report" round-robins position
    buckets only, single tamper class."""
    if payload not in ("random", "report"):
        raise ValueError(f"unknown payload {payload!r}")
    n_genuine = n // 2
    n_tampered = n - n_genuine
    items = []
    seed = seed_start
    gen_module = report_payload if payload == "report" else shamb
    for _ in range(n_genuine):
        g = gen_module.generate_genuine(seed=seed, n_blocks=n_blocks)
        items.append({"kind": "genuine", "trace": g, "tamper_class": None, "bucket": None, "seed": seed})
        seed += 1
    if payload == "report":
        for i in range(n_tampered):
            bucket = BUCKETS[i % len(BUCKETS)]
            t = report_payload.generate_tampered(seed=seed, bucket=bucket, n_blocks=n_blocks)
            items.append({"kind": "tampered", "trace": t, "tamper_class": "addition", "bucket": bucket, "seed": seed})
            seed += 1
    else:
        combos = [(c, b) for c in SHA_TAMPER_CLASSES for b in BUCKETS]
        for i in range(n_tampered):
            cls, bucket = combos[i % len(combos)]
            if cls == "addition":
                t = shamb.generate_tampered(seed=seed, bucket=bucket, n_blocks=n_blocks)
            elif cls == "bitwise":
                t = shatc.generate_tampered_bitwise(seed=seed, bucket=bucket, n_blocks=n_blocks)
            else:
                t = shatc.generate_tampered_schedule_word(seed=seed, bucket=bucket, n_blocks=n_blocks)
            items.append({"kind": "tampered", "trace": t, "tamper_class": cls, "bucket": bucket, "seed": seed})
            seed += 1
    return items


def _make_sha_sample(idx, item, rendering, payload="random"):
    trace_text = shamb.render_multiblock(item["trace"], tag_op_types=True, **SHA_RENDERING_KWARGS[rendering])
    prompt = build_prompt_sha(trace_text)
    is_tampered = item["kind"] == "tampered"
    if is_tampered:
        bad = shamb.local_consistency_report(item["trace"])
        assert len(bad) == 1, f"dataset build: expected exactly one flagged line, got {bad}"
        gt_loc = list(bad[0])
    else:
        assert shamb.local_consistency_report(item["trace"]) == [], "dataset build: genuine trace not clean"
        gt_loc = [None, None, None]
    target = json.dumps({"is_tampered": is_tampered, "gt_loc": gt_loc, "op_type": item["tamper_class"]})
    return Sample(
        input=prompt, target=target, id=idx,
        metadata={"kind": item["kind"], "bucket": item["bucket"], "tamper_class": item["tamper_class"],
                   "seed": item["seed"], "n_ops": (item["trace"]["n_blocks"] * 448), "payload": payload},
    )


# --------------------------------------------------------------------------
# Small-curve ECDSA dataset
# --------------------------------------------------------------------------

def _ecdsa_loc_type(trace, loc):
    """Ground-truth op TYPE of a flagged (section, op_idx, step_name) tuple,
    read directly off the trace's own records (never guessed by name -- see
    module docstring's note that e.g. "numerator" is type addition in
    add_formula but multiplication-adjacent bookkeeping differs by op kind)."""
    section, op_idx, step_name = loc
    if section == "header":
        recs = trace["header"]
    elif section == "ladder1":
        recs = trace["ladder1_ops"][op_idx]["records"]
    elif section == "ladder2":
        recs = trace["ladder2_ops"][op_idx]["records"]
    elif section == "final_add":
        recs = trace["final_op"]["records"]
    elif section == "v":
        recs = trace["final"]
    else:
        raise ValueError(f"unknown section {section!r}")  # our own data: crash loud
    for r in recs:
        if r["name"] == step_name:
            return r["type"]
    raise ValueError(f"step {step_name!r} not found in section {section!r}")


def build_ecdsa_dataset(bits, n, seed_start=1, op_type_filter=None, curve_seed=1):
    """n total: n//2 genuine + remainder tampered, round-robin across position
    buckets. If op_type_filter is set (e.g. "addition"), tampered traces are
    rejection-sampled (by seed) until the tamper's own recorded type matches --
    used for the 8-bit-vs-16-bit per-line addition error-rate validation task.
    Returns (items, curve)."""
    curve = ecdsa.Curve(bits, seed=curve_seed)
    n_genuine = n // 2
    n_tampered = n - n_genuine
    items = []
    seed = seed_start
    for _ in range(n_genuine):
        g = ecdsa.generate_genuine(curve, seed=seed)
        items.append({"kind": "genuine", "trace": g, "bucket": None, "seed": seed, "op_type": None})
        seed += 1
    got = 0
    tries = 0
    while got < n_tampered:
        bucket = BUCKETS[got % len(BUCKETS)] if op_type_filter is None else BUCKETS[tries % len(BUCKETS)]
        t = ecdsa.generate_tampered(curve, seed=seed, bucket=bucket)
        seed += 1
        tries += 1
        loc = ecdsa.local_consistency_report(t)
        assert len(loc) == 1, f"dataset build: expected exactly one flagged line, got {loc}"
        typ = _ecdsa_loc_type(t, loc[0])
        if op_type_filter is not None and typ != op_type_filter:
            assert tries < n_tampered * 200 + 200, "op_type_filter rejection sampling stalled"
            continue
        items.append({"kind": "tampered", "trace": t, "bucket": bucket, "seed": seed - 1, "op_type": typ})
        got += 1
    return items, curve


def _make_ecdsa_sample(idx, item, prompt_variant):
    trace_text = ecdsa.render_trace(item["trace"])
    prompt = build_prompt_ecdsa(trace_text, prompt_variant)
    is_tampered = item["kind"] == "tampered"
    if is_tampered:
        bad = ecdsa.local_consistency_report(item["trace"])
        assert len(bad) == 1, f"dataset build: expected exactly one flagged line, got {bad}"
        gt_loc = list(bad[0])
    else:
        assert ecdsa.local_consistency_report(item["trace"]) == [], "dataset build: genuine trace not clean"
        gt_loc = [None, None, None]
    target = json.dumps({"is_tampered": is_tampered, "gt_loc": gt_loc, "op_type": item["op_type"]})
    return Sample(
        input=prompt, target=target, id=idx,
        metadata={"kind": item["kind"], "bucket": item["bucket"], "tamper_class": item["op_type"],
                   "seed": item["seed"], "n_ops": ecdsa.total_line_count(item["trace"]),
                   "renderer_version": ecdsa.RENDERER_VERSION},
    )


# --------------------------------------------------------------------------
# Real P-256 verification-fragment dataset (PRIMARY family)
# --------------------------------------------------------------------------

def _p256_loc_type(fragment, loc):
    """Ground-truth op TYPE of a flagged (op_idx, step_name) tuple, read
    directly off the fragment's own records (same discipline as
    _ecdsa_loc_type -- never guessed by name)."""
    op_idx, step_name = loc
    for r in fragment["ops"][op_idx]["records"]:
        if r["name"] == step_name:
            return r["type"]
    raise ValueError(f"step {step_name!r} not found in op {op_idx}")


def build_p256_dataset(n_ops, n, seed_start=1, limb_bits=8):
    """n total: n//2 genuine + remainder tampered, round-robin across
    position buckets (early/middle/late within the fragment's own op list)."""
    n_genuine = n // 2
    n_tampered = n - n_genuine
    items = []
    seed = seed_start
    for _ in range(n_genuine):
        g = p256.generate_genuine_fragment(seed=seed, n_ops=n_ops, limb_bits=limb_bits)
        items.append({"kind": "genuine", "gen": g, "bucket": None, "seed": seed, "op_type": None})
        seed += 1
    for i in range(n_tampered):
        bucket = BUCKETS[i % len(BUCKETS)]
        t = p256.generate_tampered_fragment(seed=seed, n_ops=n_ops, bucket=bucket, limb_bits=limb_bits)
        loc = p256.local_consistency_report(t["fragment"], limb_bits)
        assert len(loc) == 1, f"dataset build: expected exactly one flagged line, got {loc}"
        typ = _p256_loc_type(t["fragment"], loc[0])
        items.append({"kind": "tampered", "gen": t, "bucket": bucket, "seed": seed, "op_type": typ})
        seed += 1
    return items


def _make_p256_sample(idx, item, limb_bits=8):
    trace_text = p256.render_fragment(item["gen"])
    prompt = build_prompt_p256(trace_text)
    is_tampered = item["kind"] == "tampered"
    if is_tampered:
        bad = p256.local_consistency_report(item["gen"]["fragment"], limb_bits)
        assert len(bad) == 1, f"dataset build: expected exactly one flagged line, got {bad}"
        gt_loc = list(bad[0])
    else:
        assert p256.local_consistency_report(item["gen"]["fragment"], limb_bits) == [], \
            "dataset build: genuine fragment not clean"
        gt_loc = [None, None]
    target = json.dumps({"is_tampered": is_tampered, "gt_loc": gt_loc, "op_type": item["op_type"]})
    return Sample(
        input=prompt, target=target, id=idx,
        metadata={"kind": item["kind"], "bucket": item["bucket"], "tamper_class": item["op_type"],
                   "seed": item["seed"], "n_ops": p256.total_line_count(item["gen"]),
                   "renderer_version": p256.RENDERER_VERSION},
    )


# --------------------------------------------------------------------------
# Scorer
# --------------------------------------------------------------------------

@scorer(metrics=[accuracy(), stderr()])
def r4r_frontier_scorer(family, model_key, rung_label, reasoning_effort, max_tokens,
                         rendering, prompt_variant):
    async def do_score(state: TaskState, target: Target) -> Score:
        gt = json.loads(target.text)
        text = state.output.completion
        parsed = parse_response_frontier(text, family)
        gt_loc = tuple(gt["gt_loc"])
        outcome = score_frontier(gt["is_tampered"], gt_loc, parsed)
        correct = outcome in ("TN", "TP_r4r")
        api_model = getattr(state.output, "model", None) or model_key
        return Score(
            value=CORRECT if correct else INCORRECT,
            answer=f"verdict={parsed['verdict']} loc={parsed['loc']} p={parsed['p_tampered']}",
            explanation=outcome,
            metadata={
                "outcome": outcome,
                "verdict": parsed["verdict"],
                "loc": list(parsed["loc"]),
                "verdict_source": parsed["verdict_source"],
                "p_tampered": parsed["p_tampered"],
                "p_source": parsed["p_source"],
                "p_malformed": parsed["p_malformed"],
                "disagreement": parsed["disagreement"],
                "gt_is_tampered": gt["is_tampered"],
                "gt_loc": list(gt_loc),
                "op_type": gt.get("op_type"),  # per-op-type audit field (proposal.md's Mixed operation types)
                "kind": state.metadata["kind"],
                "bucket": state.metadata.get("bucket"),
                "seed": state.metadata["seed"],
                "n_ops": state.metadata["n_ops"],
                "payload": state.metadata.get("payload"),  # 'random'|'report' (sha only; None for ecdsa)
                "renderer_version": state.metadata.get("renderer_version"),  # ecdsa/p256 only; None for sha
                "model_key": model_key,
                "api_model": api_model,
                "eci": ECI_SCORES.get(model_key),
                "reasoning_effort": reasoning_effort,
                "max_tokens": max_tokens,
                "family": family,
                "rung": rung_label,
                "rendering": rendering,
                "prompt_variant": prompt_variant,
                "git_commit": GIT_COMMIT,
            },
        )
    return do_score


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------

@task
def verification_frontier(family: str, model_key: str, rung: int, n: int = 20,
                           seed_start: int = 1, rendering: str = None,
                           prompt_variant: str = "base", op_type_filter: str = None,
                           curve_seed: int = 1, payload: str = "random", limb_bits: int = 8,
                           reasoning_effort: str = None, max_tokens: int = None):
    """family: 'sha', 'ecdsa' (small-curve), or 'p256' (real, PRIMARY). rung:
    n_blocks (sha), field bits (ecdsa), or n_ops (p256, contiguous fragment
    length: 1/2/4/8). n: total samples (roughly half genuine, half
    tampered). rendering: 'dual'|'decimal_densified' (sha only, default
    'dual'). prompt_variant: 'base'|'recheck_reminder' (ecdsa only, the
    rendering-optimization pass). op_type_filter: e.g. 'addition' (ecdsa
    only, the 8-vs-16-bit micro-task). payload: 'random'|'report' (sha
    only, default 'random') -- 'report' uses report_payload.py's
    attestation-report-shaped message instead of random bytes (the
    TEE-attestation-realism item), addition-tamper-class only. limb_bits:
    p256 only, default 8 (matches frontier-builder's measured token/line
    table). reasoning_effort/max_tokens override the per-model MAX_EFFORT
    defaults imported from run_experiment.py.
    """
    if model_key not in MAX_EFFORT_REASONING_PARAMS:
        raise ValueError(f"unknown model_key {model_key!r}, not in MAX_EFFORT_REASONING_PARAMS")
    if family not in ("sha", "ecdsa", "p256"):
        raise ValueError(f"unknown family {family!r}")

    default_params = MAX_EFFORT_REASONING_PARAMS[model_key] or {}
    effort = reasoning_effort if reasoning_effort is not None else default_params.get("effort")
    cap = max_tokens if max_tokens is not None else COMPLETION_MAX_TOKENS[model_key]
    config = GenerateConfig(max_tokens=cap)
    if effort:
        if effort in _VALID_REASONING_EFFORT_LITERALS:
            config.reasoning_effort = effort
        else:
            # The installed inspect_ai's GenerateConfig.reasoning_effort is a
            # closed Literal (none/minimal/low/medium/high/xhigh) that does NOT
            # include "max" -- the value run_experiment.py's
            # MAX_EFFORT_REASONING_PARAMS uses for claude-opus-4.6/4.8 and
            # claude-fable-5 (empirically confirmed 200 OK against the raw
            # OpenRouter API, just not expressible in this field). Assigning
            # config.reasoning_effort = "max" directly bypasses pydantic's
            # validate-on-construction (no validate-on-assignment) and the
            # actual HTTP call goes through fine -- confirmed by the OLD
            # opus-4.6 runs in ../data/logs_checkable/, which used
            # exactly that pattern and produced real usage data -- but
            # `read_eval_log()` on the CURRENT inspect_ai version then rejects
            # the resulting log ("Input should be 'none'...'xhigh'"), which
            # would make every one of those logs (and any new one) unreadable
            # for the cost tracking and analysis this pilot needs. Routing
            # "max" through extra_body instead avoids the Literal entirely
            # (verified: constructs, round-trips through model_dump_json ->
            # model_validate_json, and completion_params() puts it in the
            # exact same place openrouter.py's own reasoning_effort branch
            # would -- extra_body={"reasoning": {"effort": ...}}).
            config.extra_body = {"reasoning": {"effort": effort}}

    if family == "sha":
        n_blocks = int(rung)
        rendering = rendering or "dual"
        if rendering not in SHA_RENDERING_KWARGS:
            raise ValueError(f"unknown sha rendering {rendering!r}")
        items = build_sha_dataset(n_blocks, n, seed_start=seed_start, payload=payload)
        samples = [_make_sha_sample(i, it, rendering, payload=payload) for i, it in enumerate(items)]
        rung_label = f"n_blocks={n_blocks}"
    elif family == "ecdsa":
        bits = int(rung)
        items, curve = build_ecdsa_dataset(bits, n, seed_start=seed_start,
                                            op_type_filter=op_type_filter, curve_seed=curve_seed)
        samples = [_make_ecdsa_sample(i, it, prompt_variant) for i, it in enumerate(items)]
        rung_label = f"bits={bits} ({curve!r})"
    else:  # p256
        n_ops = int(rung)
        items = build_p256_dataset(n_ops, n, seed_start=seed_start, limb_bits=limb_bits)
        samples = [_make_p256_sample(i, it, limb_bits=limb_bits) for i, it in enumerate(items)]
        rung_label = f"n_ops={n_ops} (p256, limb_bits={limb_bits})"

    dataset = MemoryDataset(samples)
    return Task(
        dataset=dataset,
        solver=[generate(cache=True)],  # native Inspect cache -> free replay unless prompt/config changes
        scorer=r4r_frontier_scorer(family, model_key, rung_label, effort or "none", cap, rendering, prompt_variant),
        config=config,
    )


if __name__ == "__main__":
    # zero-API dry check: build the task for a model/family/rung and print
    # sample count + a token estimate (chars // 4, matching stage0's rough
    # estimate; token_dry_run.py has the exact tiktoken counts per rung).
    import sys as _sys
    family = _sys.argv[1] if len(_sys.argv) > 1 else "sha"
    model_key = _sys.argv[2] if len(_sys.argv) > 2 else "anthropic/claude-opus-4.6"
    rung = int(_sys.argv[3]) if len(_sys.argv) > 3 else (1 if family == "sha" else 8)
    n = int(_sys.argv[4]) if len(_sys.argv) > 4 else 6
    t = verification_frontier(family=family, model_key=model_key, rung=rung, n=n)
    lens = [len(s.input) for s in t.dataset]
    print(f"task built: family={family} model={model_key} rung={rung} n={len(t.dataset)} "
          f"config={t.config}")
    print(f"  prompt chars: min={min(lens)} max={max(lens)} ~tokens(chars/4): "
          f"min={min(lens)//4} max={max(lens)//4}")
    kinds = [s.metadata['kind'] for s in t.dataset]
    print(f"  genuine={kinds.count('genuine')} tampered={kinds.count('tampered')}")
    tc = [s.metadata['tamper_class'] for s in t.dataset if s.metadata['kind'] == 'tampered']
    print(f"  tamper classes: {sorted(set(tc))}, counts="
          f"{ {c: tc.count(c) for c in sorted(set(tc))} }")
