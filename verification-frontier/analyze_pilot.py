"""Pilot analysis: per-condition parse rates/outcomes, real costs from
logged token usage x live OpenRouter prices, and a joint logistic-in-log(N)
fit per model pooling this pilot's rungs with the parent experiment's
SHA-448 result (../results_v2.jsonl, dual rendering).

Reliability, per proposal.md's Definition section, is TAMPERED-only
detection reliability (TP_r4r rate among tampered samples) -- this is what
"tamper-detection reliability crosses 50%" in the N50 definition means, and
matches how rq3-replication's own README cites "100%/88%/52% for
opus-4.6/gpt-5.5/gpt-5" (each is exactly that model's TP_r4r/42 on the dual
SHA-448 condition, confirmed against results_v2.jsonl below).

HONESTY NOTE (Ram, carried into every number this script prints): tampers
here are single seeded bit flips, never adversarially iterated against the
verifier, and every model call runs full, uncapped chain-of-thought (no
scaffold, no budget-forcing beyond the provider's own max_completion_tokens).
Both gaps mean these reliability numbers are an upper bound on what a
verifier would achieve against an adversarial tamperer or a CoT-restricted
setting, not a general capability measurement.

Run: python3 analyze_pilot.py  (reads logs_pilot/*.eval + the parent's
results_v2.jsonl; zero new API calls, pure local computation.)
"""

import json
import os
import sys

import numpy as np
from scipy.optimize import curve_fit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inspect_ai.log import read_eval_log
from run_experiment import PRICES

HERE = os.path.dirname(__file__)
# logs_pilot: the $45-cap pilot. logs_live: the $600-cap live grid. Both
# scanned together so the joint fit pools everything measured so far;
# os.listdir() is non-recursive, so logs_pilot/prefix_leak_quarantine/ (the
# 4 pre-verdict-leak-fix ECDSA logs, moved out 2026-07-12) is never picked
# up here even though it lives inside LOG_DIRS[0].
LOG_DIRS = [os.path.join(HERE, "logs_pilot"), os.path.join(HERE, "logs_live")]
PARENT_RESULTS = os.path.join(HERE, "..", "results_v2.jsonl")

SHA_OPS_PER_BLOCK = 448


def load_parent_sha448():
    """opus-4.6 / gpt-5 TP_r4r counts at N=448 (SHA 1-block, dual rendering),
    from the parent's already-shipped n=84 (42 genuine + 42 tampered) run --
    NOT re-run here, just read. Returns {model_key: (n_tampered, n_tp_r4r, n_genuine, n_tn)}."""
    from collections import Counter
    rows_by_model = {}
    with open(PARENT_RESULTS) as f:
        for line in f:
            r = json.loads(line)
            if r.get("renderer") != "dual":
                continue
            rows_by_model.setdefault(r["model_key"], []).append(r)
    out = {}
    for mk, rows in rows_by_model.items():
        if len(rows) != 84:
            continue  # only the full n=84 dual runs (skip 2-sample probes/pilots)
        c = Counter(r["outcome"] for r in rows)
        n_tampered = sum(1 for r in rows if r["kind"] == "tampered")
        n_genuine = sum(1 for r in rows if r["kind"] == "genuine")
        out[mk] = {"n_tampered": n_tampered, "n_tp_r4r": c.get("TP_r4r", 0),
                    "n_genuine": n_genuine, "n_tn": c.get("TN", 0)}
    return out


QUARANTINE_DIR_NAME = "prefix_leak_quarantine"


def _eval_files():
    """(dir, filename) for every *.eval under each LOG_DIRS entry, RECURSIVE
    (logs_live/ uses one subfolder per concurrent launch -- see
    inspect_task_frontier's Reproduce section -- to work around a real
    inspect_ai bug: concurrent `inspect eval` processes sharing one --log-dir
    race at task-discovery time and fail with a misleading "No inspect tasks
    were found" before any API call. logs_pilot/prefix_leak_quarantine/'s
    contents are explicitly excluded by name, not just by non-recursion."""
    for d in LOG_DIRS:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x != QUARANTINE_DIR_NAME]
            for fn in sorted(files):
                if fn.endswith(".eval"):
                    yield root, fn


def load_pilot_logs():
    """Every sample from every logs_pilot/ and logs_live/ *.eval, as a flat
    list of dicts."""
    rows = []
    for d, fn in _eval_files():
        log = read_eval_log(os.path.join(d, fn))
        for s in log.samples:
            sc = s.scores["r4r_frontier_scorer"]
            rows.append({
                "file": fn,
                "family": sc.metadata["family"],
                "rung": sc.metadata["rung"],
                "model_key": sc.metadata["model_key"],
                "kind": sc.metadata["kind"],
                "outcome": sc.metadata["outcome"],
                "op_type": sc.metadata.get("op_type"),
                "n_ops": sc.metadata["n_ops"],
                "verdict_source": sc.metadata["verdict_source"],
                "rendering": sc.metadata.get("rendering"),
                "prompt_variant": sc.metadata.get("prompt_variant"),
                "payload": sc.metadata.get("payload"),
                "renderer_version": sc.metadata.get("renderer_version"),
            })
    return rows


def file_costs():
    """Per-file (model_key, n_calls, cost) from each .eval's aggregate usage
    stats x PRICES (Inspect logs store tokens, not cost -- same convention as
    ../run_experiment.py's call_cost)."""
    out = []
    for d, fn in _eval_files():
        log = read_eval_log(os.path.join(d, fn))
        n_samples = len(log.samples)
        family = log.samples[0].scores["r4r_frontier_scorer"].metadata["family"]
        rung = log.samples[0].scores["r4r_frontier_scorer"].metadata["rung"]
        for api_model, usage in (log.stats.model_usage or {}).items():
            model_key = api_model.split("openrouter/", 1)[-1]
            pin, pout = PRICES[model_key]
            cost = usage.input_tokens / 1e6 * pin + usage.output_tokens / 1e6 * pout
            out.append({"file": fn, "family": family, "rung": rung, "model_key": model_key,
                        "n_samples": n_samples, "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "reasoning_tokens": usage.reasoning_tokens, "cost": cost})
    return out


def logistic(x, a, b):
    return 1.0 / (1.0 + np.exp(-(a + b * x)))


def fit_n50(points):
    """points: list of (N, is_tp_r4r 0/1) individual TAMPERED-sample outcomes
    (not aggregated rates) across every rung for one model. Fits p(N) via
    logistic regression in log(N) (MLE, statsmodels-free via scipy curve_fit
    on binned rates when n is tiny, else per-sample). Returns (N50, a, b) or
    None if not enough variation to fit (e.g. all-1 or all-0 -> no crossing,
    or fewer than 2 distinct N values)."""
    Ns = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    if len(set(Ns.tolist())) < 2:
        return None  # can't fit a slope from one rung
    if ys.sum() == 0 or ys.sum() == len(ys):
        return None  # perfectly separated -> MLE diverges; report as bound instead
    logN = np.log(Ns)
    try:
        popt, _ = curve_fit(logistic, logN, ys, p0=[0.0, 1.0], maxfev=5000)
    except RuntimeError:
        return None
    a, b = popt
    if b == 0:
        return None
    n50 = np.exp(-a / b)
    return n50, a, b


def n_at_reliability(a, b, target):
    """N at which the fitted logistic crosses `target` reliability (e.g. 0.9
    for N90, per Ram's requirement that every grid analysis report BOTH N50
    -- METR comparability -- and N90 -- the deployment-relevant threshold).
    Solves a + b*log(N) = logit(target) for N. Since b < 0 here (reliability
    DECREASES with N), N90 < N50 always -- N90 is a stricter, shorter-length
    bound, matching "N90 sits well below N50" from the team lead's note."""
    logit_target = np.log(target / (1 - target))
    return np.exp((logit_target - a) / b)


def bootstrap_n_ci(points, target, n_resample=2000, seed=0, alpha=0.10):
    """Percentile bootstrap CI (default 90%, alpha=0.10) for N at `target`
    reliability: resample (N, y) pairs with replacement, refit, recompute,
    repeat. Returns (lo, hi) or None if too few resamples produce a valid
    fit (e.g. every resample perfectly separated -- expect this to be common
    and WIDE given this grid's small per-point n; report None honestly
    rather than a fabricated-looking interval)."""
    rng = np.random.RandomState(seed)
    idx = np.arange(len(points))
    vals = []
    for _ in range(n_resample):
        sample_idx = rng.choice(idx, size=len(idx), replace=True)
        sample = [points[i] for i in sample_idx]
        fit = fit_n50(sample)
        if fit is None:
            continue
        n50, a, b = fit
        n_val = n50 if target == 0.5 else n_at_reliability(a, b, target)
        if np.isfinite(n_val) and n_val > 0:
            vals.append(n_val)
    if len(vals) < n_resample * 0.1:  # fewer than 10% of resamples gave a usable fit -> CI unreliable
        return None
    vals.sort()
    lo = vals[int((alpha / 2) * len(vals))]
    hi = vals[int((1 - alpha / 2) * len(vals))]
    return lo, hi


def main():
    print("=== Per-file real cost (tokens x live OpenRouter prices) ===")
    costs = file_costs()
    total = 0.0
    for c in costs:
        print(f"  {c['family']:6s} {c['rung']:35s} {c['model_key']:28s} n={c['n_samples']} "
              f"in={c['input_tokens']:>7} out={c['output_tokens']:>7} reasoning={c['reasoning_tokens']:>7} "
              f"cost=${c['cost']:.2f} (${c['cost']/c['n_samples']:.3f}/call)")
        total += c["cost"]
    print(f"  PILOT+LIVE TOTAL SO FAR: ${total:.2f} (pilot cap $45, live-grid cap $600)")

    print("\n=== Per-condition outcomes ===")
    rows = load_pilot_logs()
    from collections import Counter, defaultdict
    by_cond = defaultdict(list)
    for r in rows:
        # payload included: report-shaped and random-payload SHA samples at the
        # SAME rung are different conditions (the report-shaped batch is a
        # parity CHECK against random-payload, not more data for the same
        # condition) -- pooling them silently would be a real methodological
        # error, caught when this key omitted payload and merged them.
        by_cond[(r["family"], r["rung"], r["model_key"], r["rendering"], r["prompt_variant"], r["payload"])].append(r)
    for key, rs in sorted(by_cond.items(), key=lambda kv: str(kv[0])):
        family, rung, mk, rendering, pv, payload = key
        n_tampered = sum(1 for r in rs if r["kind"] == "tampered")
        n_genuine = sum(1 for r in rs if r["kind"] == "genuine")
        tp_r4r = sum(1 for r in rs if r["kind"] == "tampered" and r["outcome"] == "TP_r4r")
        tn = sum(1 for r in rs if r["kind"] == "genuine" and r["outcome"] == "TN")
        unparse = sum(1 for r in rs if r["outcome"] == "UNPARSEABLE")
        print(f"  {family:6s} {rung:35s} {mk:28s} rendering={rendering} variant={pv} payload={payload}: "
              f"tampered r4r={tp_r4r}/{n_tampered} genuine TN={tn}/{n_genuine} UNPARSEABLE={unparse} "
              f"outcomes={dict(Counter(r['outcome'] for r in rs))}")

    print("\n=== Joint logistic fit per model (this pilot's rungs + parent SHA-448) ===")
    print("HONESTY NOTE: non-adversarial single-bit-flip tampers, full uncapped CoT -- see module docstring.")
    # Fit SEPARATELY per (model, family_group) rather than pooling toy (sha +
    # toy-ecdsa) with real (p256) onto one curve. This is not just caution --
    # o3's pooled data produced a NEGATIVE-width bracket (100% at N=231 toy,
    # but 0/4 r4r at N=202-321 REAL, interleaved, non-monotonic), because toy
    # and real genuinely do NOT overlay for o3: real P-256 is harder at
    # matched-or-smaller op count. That is itself the proposal's own
    # pre-registered "divergence" finding, not a fit artifact to paper over
    # by pooling -- see proposal.md's Headline deliverable section.
    parent = load_parent_sha448()
    points_by_group = defaultdict(list)  # (model_key, "toy"|"real") -> [(N, y), ...]
    unparseable_by_model = defaultdict(list)
    for mk, d in parent.items():
        n_tp = d["n_tp_r4r"]
        n_total = d["n_tampered"]
        for i in range(n_total):
            points_by_group[(mk, "toy")].append((SHA_OPS_PER_BLOCK, 1 if i < n_tp else 0))
    for r in rows:
        if r["kind"] != "tampered":
            continue
        if r["payload"] == "report":
            continue  # parity CHECK against random-payload, reported separately below, not pooled into the main fit
        n = r["n_ops"]  # actual per-sample op count (p256's bigmult decomposition varies by sample)
        group = "real" if r["family"] == "p256" else "toy"
        if r["outcome"] == "UNPARSEABLE":
            # Apparatus failure (usually: hit the model's real completion-token
            # ceiling before emitting any visible answer -- see plan.md's
            # "opus P-256 n_ops=4" entry for a verified example, stop_reason=
            # max_tokens, 0 visible chars). Excluded from the reliability fit
            # with disclosure, per the reproducibility-and-evidence skill's
            # "no mechanically-failed samples in headline numbers" rule --
            # never silently averaged in as a detection failure.
            unparseable_by_model[r["model_key"]].append(n)
            continue
        points_by_group[(r["model_key"], group)].append((n, 1 if r["outcome"] == "TP_r4r" else 0))

    for mk, ns in sorted(unparseable_by_model.items()):
        print(f"  APPARATUS FAILURE (excluded from fit, not counted as non-detection): {mk} "
              f"UNPARSEABLE at N={sorted(set(ns))} ({len(ns)} samples)")

    for (mk, group), pts in sorted(points_by_group.items()):
        Ns = sorted(set(p[0] for p in pts))
        rates = {n: (sum(y for x, y in pts if x == n), sum(1 for x, y in pts if x == n)) for n in Ns}
        rate_str = ", ".join(f"N={n}: {k}/{m} ({k/m:.0%})" for n, (k, m) in rates.items())
        label = f"{mk} [{group}]"
        fit = fit_n50(pts)
        if fit is None:
            direction = "all-100%" if all(y == 1 for _, y in pts) else ("all-0%" if all(y == 0 for _, y in pts) else "insufficient rung spread")
            print(f"  {label}: rungs [{rate_str}] -> NO FIT ({direction}); N50/N90 not identified from this data, "
                  f"only a bound (still {direction[4:] if direction.startswith('all-') else 'ambiguous'} at tested lengths)")
            continue
        n50, a, b = fit
        n90 = n_at_reliability(a, b, 0.9)
        rate_vals = {n: k / m for n, (k, m) in rates.items()}
        no_intermediate = all(v in (0.0, 1.0) for v in rate_vals.values())
        hundred_ns = [n for n, v in rate_vals.items() if v == 1.0]
        zero_ns = [n for n, v in rate_vals.items() if v == 0.0]
        # Bracket only if the two clusters are properly ordered (every 100%
        # rung below every 0% rung) -- if they're interleaved/non-monotonic,
        # neither a bracket NOR the fit's point estimate is trustworthy;
        # report the raw non-monotonic pattern instead of a fabricated range.
        monotonic_bracket = no_intermediate and hundred_ns and zero_ns and max(hundred_ns) < min(zero_ns)
        non_monotonic = no_intermediate and hundred_ns and zero_ns and not monotonic_bracket

        if non_monotonic:
            print(f"  {label}: rungs [{rate_str}] -> NON-MONOTONIC (100% and 0% rungs interleaved, not "
                  f"cleanly separated by length) -- NO bracket, NO point estimate trustworthy from this "
                  f"data; likely means this model's reliability on this family isn't well-modeled as a "
                  f"smooth function of op count alone at this n, or (for 'real') toy-vs-real divergence "
                  f"is real and this group needs its own denser sampling, not a shared curve")
            continue

        ci50 = bootstrap_n_ci(pts, 0.5) if not monotonic_bracket else None
        ci90 = bootstrap_n_ci(pts, 0.9) if not monotonic_bracket else None

        def _fmt(lbl, n_val, ci):
            if monotonic_bracket:
                lo, hi = max(hundred_ns), min(zero_ns)
                return (f"{lbl} BRACKETED in ({lo}, {hi}) ops, NOT further localized "
                        f"(every tested rung is 0% or 100%, no intermediate point constrains the "
                        f"transition; fit crossing={n_val:,.0f} is where the fit places it, not a "
                        f"real estimate)")
            ci_str = f", 90% CI [{ci[0]:,.0f}, {ci[1]:,.0f}]" if ci else ", CI: bootstrap unreliable at this n (too few resamples converge)"
            return f"{lbl}~={n_val:,.0f} ops{ci_str}"

        print(f"  {label}: rungs [{rate_str}] -> {_fmt('N50', n50, ci50)}, {_fmt('N90', n90, ci90)} "
              f"(a={a:.3f}, b={b:.4f})")


if __name__ == "__main__":
    main()
