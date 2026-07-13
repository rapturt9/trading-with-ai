"""Phase 3 plots, regenerated from results/checkable.jsonl (Arm A, dual renderer) and
results/raw_maxeffort.jsonl (Phase 1b baseline). No API calls. Colorblind-safe,
CI error bars, one axis, direct-labeled points (dataviz skill).

Outputs (plots/):
  detection_vs_capability.png    - mechanism-aware detection vs ECI, 95% Wilson CI
  specificity_vs_capability.png      - genuine-specificity vs ECI, 95% Wilson CI
  raw_vs_checkable_detection.png      - before/after grouped bars, per model

Run: python3 make_plots_checkable.py
"""

import json
import math
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from run_experiment import ECI_SCORES

_REPO = os.path.join(os.path.dirname(__file__), "..")
PLOTS = os.path.join(_REPO, "plots")
RESULTS_CHECKABLE = os.path.join(_REPO, "results", "checkable.jsonl")
RESULTS_MAXEFFORT = os.path.join(_REPO, "results", "raw_maxeffort.jsonl")
LABEL = {"openai/gpt-4o": "gpt-4o", "openai/o3": "o3", "openai/gpt-5": "gpt-5",
         "anthropic/claude-opus-4.6": "opus-4.6", "openai/gpt-5.5": "gpt-5.5"}
ARM_A = list(LABEL)

# colorblind-safe (Okabe-Ito subset)
C_P3 = "#0072B2"   # blue  = Phase 3
C_P1B = "#E69F00"  # orange = Phase 1b
C_ACCENT = "#0072B2"


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def load_phase3():
    """Arm A dual per-model: (tp_r4r, n_tampered, tn, n_genuine)."""
    recs = defaultdict(list)
    for line in open(RESULTS_CHECKABLE):
        r = json.loads(line)
        if r["renderer"] == "dual":
            recs[r["model_key"]].append(r)
    out = {}
    for mk, rs in recs.items():
        tamp = [r for r in rs if r["kind"] == "tampered"]
        gen = [r for r in rs if r["kind"] == "genuine"]
        out[mk] = {
            "tp": sum(1 for r in tamp if r["outcome"] == "TP_r4r"), "nt": len(tamp),
            "tn": sum(1 for r in gen if r["outcome"] == "TN"), "ng": len(gen),
        }
    return out


def load_phase1b():
    """Phase 1b per-model TP_r4r + TN from results/raw_maxeffort.jsonl."""
    recs = defaultdict(lambda: {"tp": 0, "nt": 0, "tn": 0, "ng": 0})
    for line in open(RESULTS_MAXEFFORT):
        r = json.loads(line)
        # results_maxeffort rows: {model, kind, outcome, tier, ...}
        mk = r["model"]
        d = recs[mk]
        if r["kind"] == "tampered":
            d["nt"] += 1
            if r["outcome"] == "TP_r4r":
                d["tp"] += 1
        else:
            d["ng"] += 1
            if r["outcome"] == "TN":
                d["tn"] += 1
    return recs


def scatter_vs_eci(p3, key_num, key_den, title, ylabel, fname):
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    xs, ys, los, his, labels = [], [], [], [], []
    for mk in ARM_A:
        if mk not in p3:
            continue
        k, n = p3[mk][key_num], p3[mk][key_den]
        p, lo, hi = wilson(k, n)
        xs.append(ECI_SCORES[mk]); ys.append(p * 100)
        los.append((p - lo) * 100); his.append((hi - p) * 100)
        labels.append(f"{LABEL[mk]}\n{k}/{n}")
    ax.errorbar(xs, ys, yerr=[los, his], fmt="o", color=C_ACCENT, ecolor=C_ACCENT,
                elinewidth=2, capsize=4, markersize=9, markeredgecolor="white",
                markeredgewidth=1.5, zorder=3)
    for x, y, lab in zip(xs, ys, labels):
        ax.annotate(lab, (x, y), textcoords="offset points", xytext=(9, 4),
                    fontsize=9, color="#222222")
    ax.set_xlabel("Epoch Capability Index (ECI)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, weight="bold")
    ax.set_ylim(-5, 105)
    ax.grid(True, axis="y", color="#DDDDDD", linewidth=0.8, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, fname), dpi=150)
    plt.close(fig)
    print(f"wrote plots/{fname}")


def before_after(p3, p1b, fname):
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    labels, y1b, y3 = [], [], []
    for mk in ARM_A:
        if mk not in p3:
            continue
        labels.append(LABEL[mk])
        y1b.append(100 * p1b[mk]["tp"] / p1b[mk]["nt"] if p1b[mk]["nt"] else 0)
        y3.append(100 * p3[mk]["tp"] / p3[mk]["nt"] if p3[mk]["nt"] else 0)
    x = range(len(labels))
    w = 0.38
    ax.bar([i - w / 2 for i in x], y1b, w, label="raw trace (binary arithmetic)",
           color=C_P1B, zorder=3)
    ax.bar([i + w / 2 for i in x], y3, w, label="same trace, rendered for checking",
           color=C_P3, zorder=3)
    for i, (a, b) in enumerate(zip(y1b, y3)):
        ax.annotate(f"{a:.0f}", (i - w / 2, a), ha="center", va="bottom", fontsize=8.5, color="#222")
        ax.annotate(f"{b:.0f}", (i + w / 2, b), ha="center", va="bottom", fontsize=8.5, color="#222")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylabel("Tamper caught, exact round named (%, higher is better)")
    ax.set_title("Same 84 traces, two renderings: tamper detection",
                 fontsize=12, weight="bold")
    ax.set_ylim(0, 105)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(True, axis="y", color="#DDDDDD", linewidth=0.8, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, fname), dpi=150)
    plt.close(fig)
    print(f"wrote plots/{fname}")


if __name__ == "__main__":
    os.makedirs(PLOTS, exist_ok=True)
    p3 = load_phase3()
    p1b = load_phase1b()
    scatter_vs_eci(p3, "tp", "nt",
                   "Checkable rendering: tamper detection vs capability",
                   "Tamper caught, exact round named (% of 42)", "detection_vs_capability.png")
    scatter_vs_eci(p3, "tn", "ng",
                   "Checkable rendering: genuine traces passed vs capability",
                   "Genuine traces correctly passed (% of 42)", "specificity_vs_capability.png")
    before_after(p3, p1b, "raw_vs_checkable_detection.png")
