"""
Generate the three Phase-3 figures for the "Making credible deals with AIs" post.

Two of the three lines in every figure are REAL Phase-1b measurements (max
reasoning effort, n=42 per condition, from README.md's Phase 1b tables). The
Phase-3 line/band is the PRE-REGISTERED PREDICTION written before any Phase-3
run (rq3-replication/plan.md, "PRE-REGISTERED PREDICTION" block, 2026-07-11),
NOT a measurement. Every title and caption says EXPECTED so no one mistakes the
prediction for data.

Re-pointing to real results when Phase 3 finishes
-------------------------------------------------
Set PHASE3_SOURCE = "measured" and point RESULTS_V2 at the completed
results_v2.jsonl. `load_phase3_measured()` aggregates per-model TP_r4r,
genuine-specificity and false-flag rates straight from the scored rows, and the
titles/captions drop the EXPECTED tag automatically. Nothing else changes, so
the figures regenerate as data figures with one flag flip.

    python3 plots/make_expected_plots.py
"""
import json
import math
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# ---------------------------------------------------------------------------
# Config: expected (default, prediction) vs measured (flip when Phase 3 lands)
# ---------------------------------------------------------------------------
PHASE3_SOURCE = "expected"          # "expected" | "measured"
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_V2 = os.path.join(HERE, "..", "results_v2.jsonl")
N = 42                               # traces per condition (Arm A, per model)

IS_EXPECTED = PHASE3_SOURCE == "expected"
TAG = "EXPECTED (pre-registered), pending results" if IS_EXPECTED else "measured, Phase 3 Arm A"

# Palette (colorblind-friendly)
C_MEASURED = "#4878CF"   # Phase 1b measured
C_EXPECTED = "#6ACC65"   # Phase 3 expected
C_BAD = "#D65F5F"

# ---------------------------------------------------------------------------
# Phase 1b measured data (README.md Phase 1b, max effort, n=42/condition)
# model: (ECI, TP_r4r_hits, TN_hits, FP_hits)  each out of 42
# ---------------------------------------------------------------------------
PHASE1B = {
    "gpt-4o":          (129.3, 0,  21, 20),
    "o3":              (147.1, 1,  39, 3),
    "gpt-5":           (150.0, 0,  29, 13),
    "claude-opus-4.6": (155.5, 8,  37, 0),
    "gpt-5.5":         (158.5, 5,  34, 8),
}
ORDER = ["gpt-4o", "o3", "gpt-5", "claude-opus-4.6", "gpt-5.5"]


def pct(hits, n=N):
    return 100.0 * hits / n


def se_pct(hits, n=N):
    p = hits / n
    return 100.0 * math.sqrt(p * (1 - p) / n)


# ---------------------------------------------------------------------------
# Phase 3 numbers. In "expected" mode these come from the pre-registered
# prediction. In "measured" mode they are computed from results_v2.jsonl.
# ---------------------------------------------------------------------------
def load_phase3_measured(path):
    """Aggregate per-model Phase-3 metrics from a completed results_v2.jsonl.

    Returns {model_key: {"eci", "tp_r4r_pct", "spec_pct", "fp_pct", "n_tamp",
    "n_gen"}}. Row schema (see rq3-replication/results_v2.jsonl): one scored
    trace per line with `model_key`, `kind` in {genuine, tampered}, `outcome`
    in {TP_r4r, TP_wrong_round, FN, TN, FP, UNPARSEABLE}, and `eci`.
    """
    rows = [json.loads(l) for l in open(path)]
    by_model = {}
    for r in rows:
        by_model.setdefault(r["model_key"], []).append(r)
    out = {}
    for mk, rs in by_model.items():
        tamp = [r for r in rs if r["kind"] == "tampered"]
        gen = [r for r in rs if r["kind"] == "genuine"]
        n_t, n_g = len(tamp), len(gen)
        out[mk] = {
            "eci": rs[0]["eci"],
            "n_tamp": n_t,
            "n_gen": n_g,
            "tp_r4r_pct": 100.0 * sum(r["outcome"] == "TP_r4r" for r in tamp) / n_t if n_t else None,
            "spec_pct": 100.0 * sum(r["outcome"] == "TN" for r in gen) / n_g if n_g else None,
            "fp_pct": 100.0 * sum(r["outcome"] == "FP" for r in gen) / n_g if n_g else None,
        }
    return out


# Pre-registered prediction (plan.md). Firm point commitments:
#   best committed model TP_r4r in 40-65%; genuine-specificity >= 80%;
#   AUROC >= 0.80; gpt-4o stays near 0% (no reasoning channel);
#   detection roughly monotone in ECI. The rising band below illustrates that
#   monotone shape; only the 40-65% top-model point and the gpt-4o ~0 point
#   are hard commitments.
PRED_TOP_BAND = (40.0, 65.0)        # best-model TP_r4r
PRED_SPEC_FLOOR = 80.0              # genuine-specificity floor
PRED_GPT4O_DETECT = 2.0            # near zero, no reasoning channel
# expected detection band edges as a function of ECI, over the reasoning
# models only (o3 .. gpt-5.5), rising into the 40-65% top-model band.
BAND_ECI = (147.1, 158.5)
BAND_LOWER = (15.0, 40.0)           # lower edge at (o3 ECI, top ECI)
BAND_UPPER = (35.0, 65.0)           # upper edge


def interp(x, xs, ys):
    return ys[0] + (ys[1] - ys[0]) * (x - xs[0]) / (xs[1] - xs[0])


# ---------------------------------------------------------------------------
# Shared style helpers
# ---------------------------------------------------------------------------
def clean(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=12)
    ax.grid(axis="y", alpha=0.25)


def expected_title(base):
    if IS_EXPECTED:
        return base + "\nPhase 3 line is EXPECTED (pre-registered), pending results"
    return base + "\nPhase 3 line is measured (Arm A)"


# ---------------------------------------------------------------------------
# Figure 1: mechanism-aware detection vs ECI
# ---------------------------------------------------------------------------
def fig_detection_vs_eci(phase3):
    fig, ax = plt.subplots(figsize=(11, 7))

    xs = [PHASE1B[m][0] for m in ORDER]
    ys = [pct(PHASE1B[m][1]) for m in ORDER]
    es = [1.96 * se_pct(PHASE1B[m][1]) for m in ORDER]
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color=C_MEASURED, markersize=10,
                capsize=5, linewidth=2, zorder=4,
                label="Phase 1b measured (unoptimized trace, n=42/model)")
    for m in ORDER:
        eci, hits = PHASE1B[m][0], PHASE1B[m][1]
        ax.annotate(f"{m}\n{pct(hits):.0f}%", (eci, pct(hits)),
                    textcoords="offset points", xytext=(6, 12), fontsize=9,
                    color=C_MEASURED)

    if IS_EXPECTED:
        lo = [interp(e, BAND_ECI, BAND_LOWER) for e in [BAND_ECI[0], BAND_ECI[1]]]
        hi = [interp(e, BAND_ECI, BAND_UPPER) for e in [BAND_ECI[0], BAND_ECI[1]]]
        ax.fill_between(list(BAND_ECI), lo, hi, color=C_EXPECTED, alpha=0.30,
                        hatch="//", edgecolor=C_EXPECTED, linewidth=0, zorder=2,
                        label="Phase 3 EXPECTED band (pre-registered): detection\n"
                              "rises into 40-65% for the top models")
        # top-model target marker
        ax.annotate("pre-registered target\nfor best model: 40-65%",
                    xy=(158.5, 52.5), xytext=(150.5, 74),
                    fontsize=10, color="#2f7d2f",
                    arrowprops=dict(arrowstyle="->", color="#2f7d2f"))
        # gpt-4o stays near 0 (no reasoning channel)
        ax.scatter([129.3], [PRED_GPT4O_DETECT], marker="s", s=70,
                   color=C_EXPECTED, zorder=5)
        ax.annotate("gpt-4o expected ~0%\n(no reasoning channel)", (129.3, PRED_GPT4O_DETECT),
                    textcoords="offset points", xytext=(8, 18), fontsize=9, color="#2f7d2f")
    else:
        xe = [phase3[_measured_key(m)]["eci"] for m in ORDER if _measured_key(m) in phase3]
        ye = [phase3[_measured_key(m)]["tp_r4r_pct"] for m in ORDER if _measured_key(m) in phase3]
        ax.plot(xe, ye, "s-", color=C_EXPECTED, markersize=10, linewidth=2,
                zorder=3, label="Phase 3 measured (checkability-optimized trace)")

    ax.axhspan(PRED_TOP_BAND[0], PRED_TOP_BAND[1], color=C_EXPECTED, alpha=0.06, zorder=0)
    ax.set_xlabel("Epoch Capability Index (ECI, higher = more capable)", fontsize=14)
    ax.set_ylabel("Mechanism-aware tamper detection\n(right round named, %, higher is better)", fontsize=14)
    ax.set_title(expected_title(
        "Verification jumps only when the trace is rendered for checkability"),
        fontsize=15)
    ax.set_ylim(-3, 80)
    clean(ax)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.95)
    fig.text(0.5, 0.005,
             f"Blue = Phase 1b, real API calls, max reasoning effort, n=42 tampered traces/model. "
             f"Green = {TAG}. Source: rq3-replication README Phase 1b table + plan.md pre-registered prediction.",
             ha="center", fontsize=8, wrap=True)
    fig.subplots_adjust(bottom=0.13)
    out = os.path.join(HERE, "fig_detection_vs_eci_expected.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)


# ---------------------------------------------------------------------------
# Figure 2: genuine-specificity vs ECI
# ---------------------------------------------------------------------------
def fig_specificity_vs_eci(phase3):
    fig, ax = plt.subplots(figsize=(11, 7))

    xs = [PHASE1B[m][0] for m in ORDER]
    ys = [pct(PHASE1B[m][2]) for m in ORDER]
    es = [1.96 * se_pct(PHASE1B[m][2]) for m in ORDER]
    ax.errorbar(xs, ys, yerr=es, fmt="o-", color=C_MEASURED, markersize=10,
                capsize=5, linewidth=2, zorder=4,
                label="Phase 1b measured (unoptimized trace, n=42/model)")
    for m in ORDER:
        eci, tn = PHASE1B[m][0], PHASE1B[m][2]
        ax.annotate(f"{m}\n{pct(tn):.0f}%", (eci, pct(tn)),
                    textcoords="offset points", xytext=(6, -26), fontsize=9,
                    color=C_MEASURED)

    if IS_EXPECTED:
        ax.axhspan(PRED_SPEC_FLOOR, 100, color=C_EXPECTED, alpha=0.18,
                   zorder=1, label="Phase 3 EXPECTED zone (pre-registered):\ngenuine-specificity ≥ 80%")
        ax.axhline(PRED_SPEC_FLOOR, color="#2f7d2f", linestyle="--", linewidth=1.5, zorder=2)
        ax.annotate("pre-registered floor: 80%", xy=(140, PRED_SPEC_FLOOR),
                    xytext=(133, 83.5), fontsize=10, color="#2f7d2f")
    else:
        xe = [phase3[_measured_key(m)]["eci"] for m in ORDER if _measured_key(m) in phase3]
        ye = [phase3[_measured_key(m)]["spec_pct"] for m in ORDER if _measured_key(m) in phase3]
        ax.plot(xe, ye, "s-", color=C_EXPECTED, markersize=10, linewidth=2,
                zorder=3, label="Phase 3 measured (checkability-optimized trace)")

    ax.set_xlabel("Epoch Capability Index (ECI, higher = more capable)", fontsize=14)
    ax.set_ylabel("Genuine-trace specificity\n(true genuine / 42, %, higher is better)", fontsize=14)
    ax.set_title(expected_title(
        "Optimizing the trace is predicted to hold specificity at or above 80%"),
        fontsize=15)
    ax.set_ylim(40, 102)
    clean(ax)
    ax.legend(loc="lower right", fontsize=10, framealpha=0.95)
    fig.text(0.5, 0.005,
             f"Blue = Phase 1b, real API calls, max reasoning effort, n=42 genuine traces/model. "
             f"Green = {TAG}. Source: rq3-replication README Phase 1b table + plan.md pre-registered prediction.",
             ha="center", fontsize=8, wrap=True)
    fig.subplots_adjust(bottom=0.13)
    out = os.path.join(HERE, "fig_specificity_vs_eci_expected.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)


# ---------------------------------------------------------------------------
# Figure 3: the two-sided failure, measured vs expected
# Representative model: gpt-5.5 (a named candidate best model in the
# prediction, and the one whose Phase 1b failure is visibly two-sided).
# ---------------------------------------------------------------------------
def fig_two_sided(phase3):
    fig, ax = plt.subplots(figsize=(11, 7))
    groups = ["Tampers caught\n(right round, want high)",
              "Genuine traces false-flagged\n(want low)"]
    x = [0, 1]
    w = 0.36

    # Phase 1b measured, gpt-5.5
    caught_1b = pct(PHASE1B["gpt-5.5"][1])   # 11.9%
    ff_1b = pct(PHASE1B["gpt-5.5"][3])       # 19.0%
    caught_1b_e = 1.96 * se_pct(PHASE1B["gpt-5.5"][1])
    ff_1b_e = 1.96 * se_pct(PHASE1B["gpt-5.5"][3])

    b1 = ax.bar([xi - w / 2 for xi in x], [caught_1b, ff_1b], w,
                yerr=[caught_1b_e, ff_1b_e], capsize=5,
                color=C_MEASURED, edgecolor="white",
                label="Phase 1b measured (gpt-5.5, unoptimized trace)")
    ax.text(x[0] - w / 2, caught_1b + caught_1b_e + 1.5, f"{caught_1b:.0f}%",
            ha="center", fontsize=12, fontweight="bold", color=C_MEASURED)
    ax.text(x[1] - w / 2, ff_1b + ff_1b_e + 1.5, f"{ff_1b:.0f}%",
            ha="center", fontsize=12, fontweight="bold", color=C_MEASURED)

    if IS_EXPECTED:
        caught_lo, caught_hi = PRED_TOP_BAND     # 40-65
        caught_mid = (caught_lo + caught_hi) / 2
        ff_ceiling = 100 - PRED_SPEC_FLOOR       # <= 20
        ax.bar([x[0] + w / 2], [caught_mid], w,
               yerr=[[caught_mid - caught_lo], [caught_hi - caught_mid]], capsize=6,
               color=C_EXPECTED, edgecolor="white",
               label="Phase 3 EXPECTED (pre-registered)")
        ax.bar([x[1] + w / 2], [ff_ceiling], w,
               color=C_EXPECTED, edgecolor="white", hatch="//")
        ax.text(x[0] + w / 2, caught_hi + 1.5, "40-65%",
                ha="center", fontsize=12, fontweight="bold", color="#2f7d2f")
        ax.text(x[1] + w / 2, ff_ceiling + 1.5, "≤ 20%",
                ha="center", fontsize=12, fontweight="bold", color="#2f7d2f")
    else:
        m = _measured_key("gpt-5.5")
        caught_p3 = phase3[m]["tp_r4r_pct"]
        ff_p3 = phase3[m]["fp_pct"]
        ax.bar([x[0] + w / 2], [caught_p3], w, color=C_EXPECTED, edgecolor="white",
               label="Phase 3 measured (gpt-5.5, checkability-optimized trace)")
        ax.bar([x[1] + w / 2], [ff_p3], w, color=C_EXPECTED, edgecolor="white")
        ax.text(x[0] + w / 2, caught_p3 + 1.5, f"{caught_p3:.0f}%", ha="center",
                fontsize=12, fontweight="bold", color="#2f7d2f")
        ax.text(x[1] + w / 2, ff_p3 + 1.5, f"{ff_p3:.0f}%", ha="center",
                fontsize=12, fontweight="bold", color="#2f7d2f")

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=12)
    ax.set_ylabel("Rate (% of 42 traces)", fontsize=14)
    ax.set_title(expected_title(
        "The failure is two-sided; optimizing the trace is predicted to lift both"),
        fontsize=15)
    ax.set_ylim(0, 75)
    clean(ax)
    ax.legend(loc="upper right", fontsize=10, framealpha=0.95)
    fig.text(0.5, 0.005,
             "gpt-5.5 shown as the representative model. Phase 1b best detector claude-opus-4.6 measured "
             "19% caught / 0% false-flagged. "
             f"Green bars = {TAG}. Source: README Phase 1b + plan.md prediction.",
             ha="center", fontsize=8, wrap=True)
    fig.subplots_adjust(bottom=0.13)
    out = os.path.join(HERE, "fig_two_sided_expected.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)


def _measured_key(short):
    """Map short model names to the model_key used in results_v2.jsonl."""
    return {
        "gpt-4o": "openai/gpt-4o",
        "o3": "openai/o3",
        "gpt-5": "openai/gpt-5",
        "claude-opus-4.6": "anthropic/claude-opus-4.6",
        "gpt-5.5": "openai/gpt-5.5",
    }[short]


def main():
    phase3 = None
    if not IS_EXPECTED:
        phase3 = load_phase3_measured(RESULTS_V2)
    fig_detection_vs_eci(phase3)
    fig_specificity_vs_eci(phase3)
    fig_two_sided(phase3)
    print(f"\nMode: {PHASE3_SOURCE}. Green series = {TAG}.")


if __name__ == "__main__":
    main()
