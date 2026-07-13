"""Phase 3 analysis / export: read the Inspect .eval logs in data/logs_checkable/,
stream every sample's stored score metadata to results/checkable.jsonl (one line per
(model, renderer, trace), full provenance), and compute the metric suite +
pilot gates per (model, renderer).

Every headline number is derived HERE from the saved .eval logs, so the whole
report reproduces offline from cache with zero new API calls (the .eval logs are
the artifact; re-running `inspect eval` with cache=True makes zero new calls and
this script re-derives identical numbers).

Reuses the summarize_inspect_logs.py raw-zip fallback for the inspect_ai 0.3.189
reasoning_effort="max" log-schema bug (claude models).

Run: python3 analyze_checkable.py            # export + full metric table
     python3 analyze_checkable.py --gates    # also print the pilot gate verdicts
"""

import glob
import json
import os
import sys
import zipfile
from collections import defaultdict

from score_checkable import auroc, bootstrap_auroc_ci, tpr_at_fpr, brier
from run_experiment import call_cost, PRICES_DATE

_REPO = os.path.join(os.path.dirname(__file__), "..")
LOG_DIR = os.path.join(_REPO, "data", "logs_checkable")
RESULTS = os.path.join(_REPO, "results", "checkable.jsonl")
SCORER = "r4r_v2_scorer"


def _samples_from_log(path):
    """Yield each sample's score metadata dict. Tries the pydantic reader first,
    falls back to a raw-zip read for the effort='max' schema bug."""
    try:
        from inspect_ai.log import read_eval_log
        log = read_eval_log(path)
        for s in log.samples:
            yield s.scores[SCORER].metadata
        return
    except Exception as e:
        print(f"  {os.path.basename(path)}: pydantic read failed ({type(e).__name__}), raw-zip fallback")
    z = zipfile.ZipFile(path)
    for n in z.namelist():
        if n.startswith("samples/") and n.endswith(".json"):
            d = json.loads(z.read(n))
            yield d["scores"][SCORER]["metadata"]


def load_records():
    """All per-sample records across every .eval log, keyed nowhere -- just a
    flat list with full metadata. Deduplicates by (model_key, renderer, seed):
    a re-run replay writes a new log, keep the most recent file's version."""
    records = {}
    for path in sorted(glob.glob(f"{LOG_DIR}/*.eval")):  # sorted => newest last (timestamp prefix)
        for md in _samples_from_log(path):
            key = (md["model_key"], md["renderer"], md["seed"])
            records[key] = md
    return list(records.values())


def export_jsonl(records):
    with open(RESULTS, "w") as f:
        for md in sorted(records, key=lambda m: (m["model_key"], m["renderer"], m["seed"])):
            f.write(json.dumps(md) + "\n")
    print(f"wrote {len(records)} records to {RESULTS}")


def load_usage():
    """Per unique (model_key, renderer, seed) token usage, deduped so a
    cache-replayed sample in a later log is counted ONCE (real spend = the one
    real call). Returns dict key -> (model_key, input_tok, output_tok)."""
    usage = {}
    for path in sorted(glob.glob(f"{LOG_DIR}/*.eval")):
        try:
            z = zipfile.ZipFile(path)
        except Exception:
            continue
        for n in z.namelist():
            if not (n.startswith("samples/") and n.endswith(".json")):
                continue
            try:
                d = json.loads(z.read(n))
                md = d["scores"][SCORER]["metadata"]
                mu = d.get("model_usage") or {}
                if not mu:
                    continue
                u = list(mu.values())[0]
                key = (md["model_key"], md["renderer"], md["seed"])
                usage[key] = (md["model_key"], u.get("input_tokens", 0), u.get("output_tokens", 0))
            except Exception:
                continue
    return usage


def cost_report():
    usage = load_usage()
    by_model = defaultdict(lambda: [0, 0, 0])  # [calls, in_tok, out_tok]
    for (mk, rend, seed), (model_key, it, ot) in usage.items():
        by_model[model_key][0] += 1
        by_model[model_key][1] += it
        by_model[model_key][2] += ot
    total = 0.0
    print(f"\n--- COST (computed = tokens x price, prices as of {PRICES_DATE}; "
          f"unique calls only, cache-replays counted once) ---")
    for mk in sorted(by_model):
        calls, it, ot = by_model[mk]
        c = call_cost(mk, it, ot)
        total += c
        print(f"  {mk:34s} calls={calls:3d}  in={it:>10,}  out={ot:>9,}  ${c:7.2f}")
    print(f"  {'TOTAL REAL SPEND':34s} {'':>21}${total:7.2f}   (hard stop $560)")
    return total


def group(records):
    g = defaultdict(list)
    for md in records:
        g[(md["model_key"], md["renderer"])].append(md)
    return g


def metric_suite(recs):
    """Full metric suite for one (model, renderer) group of trace records."""
    n = len(recs)
    genuine = [r for r in recs if r["kind"] == "genuine"]
    tampered = [r for r in recs if r["kind"] == "tampered"]
    oc = lambda rs: {k: sum(1 for r in rs if r["outcome"] == k) for k in
                     ("TN", "FP", "FN", "TP_r4r", "TP_wrong_round", "UNPARSEABLE")}
    g_oc, t_oc = oc(genuine), oc(tampered)

    # AUROC / TPR / Brier over p_tampered (imputed 0.5 already in metadata)
    ps = [r["p_tampered"] for r in recs]
    ys = [1 if r["kind"] == "tampered" else 0 for r in recs]
    auc = tpr = brier_v = None
    auc_ci = (None, None)
    if any(ys) and not all(ys):
        auc = auroc(ps, ys)
        auc_ci = bootstrap_auroc_ci(ps, ys, n_resample=10000, seed=0)
        tpr = tpr_at_fpr(ps, ys, max_fp=2)
        brier_v = brier(ps, ys)

    n_t = len(tampered) or 1
    n_g = len(genuine) or 1
    strict = sum(1 for r in tampered if r.get("strict_mechanism"))
    # per-addition arithmetic error rate (over reported sums)
    n_rep = sum(r["arith_n_reported"] for r in recs)
    n_err = sum(r["arith_n_error"] for r in recs)
    n_copy = sum(r["arith_n_copy"] for r in recs)
    # per-position detection
    pos = {}
    for b in ("early", "middle", "late"):
        bt = [r for r in tampered if r["bucket"] == b]
        pos[b] = (sum(1 for r in bt if r["outcome"] == "TP_r4r"), len(bt))

    return {
        "n": n, "genuine": g_oc, "tampered": t_oc,
        "detection_r4r": (t_oc["TP_r4r"], len(tampered)),
        "strict_mechanism": (strict, len(tampered)),
        "specificity_TN": (g_oc["TN"], len(genuine)),
        "binary_acc": (g_oc["TN"] + t_oc["TP_r4r"] + t_oc["TP_wrong_round"], n),
        "auroc": auc, "auroc_ci": auc_ci, "tpr_at_5fpr": tpr, "brier": brier_v,
        "unparse_genuine": g_oc["UNPARSEABLE"], "unparse_tampered": t_oc["UNPARSEABLE"],
        "arith_error_rate": (n_err / n_rep) if n_rep else None,
        "arith_reported": n_rep, "arith_copy": n_copy,
        "json_present": sum(1 for r in recs if r["json_present"]),
        "disagreement": sum(1 for r in recs if r["disagreement"]),
        "per_position": pos,
        "provenance": {k: recs[0][k] for k in
                       ("model_key", "api_model", "eci", "reasoning_effort", "max_tokens",
                        "renderer", "git_commit", "eci_snapshot_date")},
    }


def print_suite(key, s):
    mk, rend = key
    print(f"\n=== {mk}  (renderer={rend}, effort={s['provenance']['reasoning_effort']}, "
          f"api_model={s['provenance']['api_model']}) n={s['n']} ===")
    print(f"  detection r4r      : {s['detection_r4r'][0]}/{s['detection_r4r'][1]}")
    print(f"  strict mechanism   : {s['strict_mechanism'][0]}/{s['strict_mechanism'][1]}")
    print(f"  specificity (TN)   : {s['specificity_TN'][0]}/{s['specificity_TN'][1]}")
    print(f"  binary accuracy    : {s['binary_acc'][0]}/{s['binary_acc'][1]}")
    if s["auroc"] is not None:
        print(f"  AUROC              : {s['auroc']:.3f}  (95% CI {s['auroc_ci'][0]:.3f}-{s['auroc_ci'][1]:.3f})")
        print(f"  TPR@<=2/42 FP      : {s['tpr_at_5fpr']:.3f}")
        print(f"  Brier              : {s['brier']:.4f}")
    print(f"  genuine outcomes   : {s['genuine']}")
    print(f"  tampered outcomes  : {s['tampered']}")
    print(f"  UNPARSEABLE        : genuine {s['unparse_genuine']}, tampered {s['unparse_tampered']}")
    ar = s["arith_error_rate"]
    print(f"  arithmetic err rate: {ar:.4f} over {s['arith_reported']} reported sums" if ar is not None
          else "  arithmetic err rate: (no sums reported)")
    print(f"  copy-cheat sums    : {s['arith_copy']}")
    print(f"  json present       : {s['json_present']}/{s['n']}   json/final disagreements: {s['disagreement']}")
    print(f"  per-position r4r   : {s['per_position']}")


def gates(g):
    """Pilot hard-gate verdicts."""
    print("\n--- PILOT GATES ---")
    for (mk, rend), recs in sorted(g.items()):
        if rend != "dual":
            continue
        parse_ok = sum(1 for r in recs if r["json_present"] and r["verdict"] is not None)
        opus_unparse = sum(1 for r in recs if r["outcome"] == "UNPARSEABLE")
        # "real computations not copies": reported sums with a nonzero count and
        # low-ish copy fraction; report the numbers, judge per stage.
        n_with_sums = sum(1 for r in recs if r["arith_n_reported"] > 0)
        print(f"  {mk} n={len(recs)}: parse(json+final)={parse_ok}/{len(recs)}, "
              f"UNPARSEABLE={opus_unparse}, samples_reporting_sums={n_with_sums}")


if __name__ == "__main__":
    recs = load_records()
    export_jsonl(recs)
    g = group(recs)
    for key in sorted(g):
        print_suite(key, metric_suite(g[key]))
    if "--gates" in sys.argv:
        gates(g)
    if "--cost" in sys.argv or "--gates" in sys.argv:
        cost_report()
