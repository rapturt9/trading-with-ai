"""Recomputes the project's standard TN/TP_r4r/TP_wrong_round/FP/FN/UNPARSEABLE
outcome table from the Inspect .eval logs in logs_inspect/, using the
`outcome` field r4r_scorer() already stores in each sample's score metadata
(inspect_task.py) -- no re-scoring logic duplicated here.

Handles a real bug hit in inspect_ai 0.3.189: reasoning_effort="max" is
accepted by GenerateConfig for making the actual API calls, but the
persisted EvalLog.plan.config schema's Literal type does not include "max"
(only none/minimal/low/medium/high/xhigh), so read_eval_log() raises a
pydantic ValidationError on log_finish for any run using effort="max" (only
claude-opus-4.6 in this project). The underlying .eval file is NOT
corrupted (confirmed via zipfile.testzip()) -- all 84 samples' data is
present, just unreadable through the strict pydantic path. Falls back to
reading the raw sample JSON directly out of the zip for that one file.

Run: python3 summarize_inspect_logs.py
"""

import glob
import json
import zipfile
from collections import Counter

from inspect_ai.log import read_eval_log

LOG_DIR = "logs_inspect"

MODEL_KEY_TO_LABEL = {
    "openai/gpt-4o": "gpt-4o",
    "openai/o3": "o3",
    "openai/gpt-5": "gpt-5",
    "anthropic/claude-opus-4.6": "claude-opus-4.6",
    "openai/gpt-5.5": "gpt-5.5",
}


def outcomes_via_pydantic(path):
    log = read_eval_log(path)
    if len(log.samples) != 84:
        return None  # a smoke-test log (n=2/n=1), not a full live run
    model_key = log.eval.task_args.get("model_key")
    genuine, tampered = Counter(), Counter()
    for s in log.samples:
        outcome = s.scores["r4r_scorer"].metadata["outcome"]
        (genuine if s.metadata["kind"] == "genuine" else tampered)[outcome] += 1
    return model_key, genuine, tampered


def outcomes_via_raw_zip(path):
    """Fallback for the reasoning_effort="max" pydantic bug above."""
    z = zipfile.ZipFile(path)
    sample_names = [n for n in z.namelist() if n.startswith("samples/")]
    if len(sample_names) != 84:
        return None
    header = json.loads(z.read("header.json"))
    model_key = header["eval"]["task_args"].get("model_key")
    genuine, tampered = Counter(), Counter()
    for n in sample_names:
        d = json.loads(z.read(n))
        outcome = d["scores"]["r4r_scorer"]["metadata"]["outcome"]
        (genuine if d["metadata"]["kind"] == "genuine" else tampered)[outcome] += 1
    return model_key, genuine, tampered


def main():
    results = {}
    for path in sorted(glob.glob(f"{LOG_DIR}/*.eval")):
        try:
            parsed = outcomes_via_pydantic(path)
        except Exception as e:
            print(f"{path}: read_eval_log failed ({type(e).__name__}), falling back to raw zip read")
            parsed = outcomes_via_raw_zip(path)
        if parsed is None:
            continue  # smoke-test log, skip
        model_key, genuine, tampered = parsed
        results[model_key] = {"genuine": genuine, "tampered": tampered}

    print(f"{'model':<20} {'TN':>4} {'FP':>4} {'g-UNPARSE':>10}   "
          f"{'TP_r4r':>7} {'TP_wrong':>9} {'FN':>4} {'t-UNPARSE':>10}")
    for model_key, label in MODEL_KEY_TO_LABEL.items():
        if model_key not in results:
            print(f"{label:<20} NOT YET IN logs_inspect/")
            continue
        g, t = results[model_key]["genuine"], results[model_key]["tampered"]
        print(f"{label:<20} {g.get('TN', 0):>4} {g.get('FP', 0):>4} {g.get('UNPARSEABLE', 0):>10}   "
              f"{t.get('TP_r4r', 0):>7} {t.get('TP_wrong_round', 0):>9} {t.get('FN', 0):>4} "
              f"{t.get('UNPARSEABLE', 0):>10}")


if __name__ == "__main__":
    main()
