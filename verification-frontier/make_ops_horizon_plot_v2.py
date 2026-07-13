"""Ops-horizon vs release-date plot, v2: MEASURED points (this experiment's
pilot + live-grid data) replacing v1's back-calculated single-length
extrapolation (../plots/make_ops_horizon_plot.py).

Two horizons per model, per Ram's requirement (relayed by the team lead,
2026-07-12): N50 (50%-reliability trace length, METR-style comparability)
and N90 (90%-reliability trace length, the deployment-relevant threshold --
Ram's rationale: a 50%-reliable verifier LAUNDERS fakes, since a wrongly-
passed check makes the AI MORE confident in a fabrication than having no
check at all, so 90% is the bar that actually matters for deployment).

Data source: analyze_pilot.py's per-(model, family_group) logistic fits,
hardcoded below as the frozen MVP snapshot (not re-fit live here, so this
plot is reproducible without re-running analyze_pilot.py -- see plan.md's
"MVP analysis" entry for the exact analyze_pilot.py output this was read
from, and the exact command to regenerate it).

HONESTY, stated in the plot itself, not just this docstring: only gpt-5 has
a real parametric fit (crossing + bootstrap CI). o3 and opus-4.6 are
BRACKETS (the last-100% rung to the first-0%-rung), not fitted crossings --
plotted as a range bar, not a point+CI, and the trend line uses each
bracket's midpoint only as a representative x-value for the fit, clearly
labeled. This is an extrapolation from very few, mostly-bracketed points,
not a precise measurement -- exactly the caveat Ram asked for wherever N90
appears, extended here to the whole plot's honesty label.

Run: python3 make_ops_horizon_plot_v2.py   (writes verification_horizon_measured.png; no API calls)
"""
import math
import os
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = os.path.dirname(__file__)

# Release dates: gpt-4o/o3/gpt-5 "published" per proposal.md's Models table;
# claude-opus-4.6/gpt-5.5 as already used in the v1 plot (confirmed there).
RELEASE = {
    "gpt-4o": date(2024, 5, 13),
    "o3": date(2025, 4, 16),
    "gpt-5": date(2025, 8, 7),
    "claude-opus-4.6": date(2026, 2, 5),
}

# From analyze_pilot.py's 2026-07-12 MVP run (see plan.md for the full log).
# kind: "fit" (point + 90% bootstrap CI) or "bracket" (lo, hi -- last-100%
# rung to first-0%-rung, no interior point tested).
MEASURED = {
    "gpt-5": {
        "n50": {"kind": "fit", "point": 448, "ci": (25, 459)},
        "n90": {"kind": "fit", "point": 415, "ci": (24, 422)},
    },
    "o3": {
        "n50": {"kind": "bracket", "lo": 321, "hi": 448},
        "n90": {"kind": "bracket", "lo": 321, "hi": 448},
    },
    "claude-opus-4.6": {
        # Crosses the toy/real family boundary (100% on toy/SHA through 896
        # ops, 0% on real-P-256 at ~2024-2092 ops) -- see plan.md's honesty
        # note on this specific bracket: unlike o3's within-family bracket,
        # this one spans two different task families, so it is coarser than
        # a same-family bracket even though the numeric range looks similar.
        "n50": {"kind": "bracket", "lo": 896, "hi": 2024},
        "n90": {"kind": "bracket", "lo": 896, "hi": 2024},
    },
}
# gpt-4o: excluded from both trend fits, same reasoning as v1 -- 0% detection
# at every tested length (toy AND real family) reads as an engagement/
# calibration floor (it actively answers, confidently, wrongly -- see
# plan.md's "gpt-4o ECDSA" finding -- not a length-driven decay), so no N50
# or N90 is identified, plotted as an annotated floor marker only.

TEE_BAND = (1_200_000, 3_200_000)
ECDSA_BAND = (410_000, 800_000)


def _point_and_err(entry):
    """Returns (y, yerr_lo, yerr_hi, is_bracket)."""
    if entry["kind"] == "fit":
        lo, hi = entry["ci"]
        return entry["point"], entry["point"] - lo, hi - entry["point"], False
    lo, hi = entry["lo"], entry["hi"]
    mid = (lo * hi) ** 0.5  # geometric mean, appropriate on a log axis
    return mid, mid - lo, hi - mid, True


def _fit_trend(xs_dates, ys):
    xo = [mdates.date2num(x) for x in xs_dates]
    ly = [math.log10(y) for y in ys]
    n = len(xo)
    sx, sy = sum(xo), sum(ly)
    sxx = sum(a * a for a in xo)
    sxy = sum(a * b for a, b in zip(xo, ly))
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    inter = (sy - slope * sx) / n
    return slope, inter


def main():
    fig, ax = plt.subplots(figsize=(11, 7))

    colors = {"n50": "#0072B2", "n90": "#D55E00"}
    markers = {"n50": "o", "n90": "^"}
    trend_lines = {}
    # Vertical label offset per model, staggered by release-date order, so
    # the 3 clustered points (o3/gpt-5/opus all within ~7 months) don't
    # overlap -- purely a layout fix, not a data change.
    label_dy = {"gpt-5": 46, "o3": -46, "claude-opus-4.6": 46}

    for horizon in ("n50", "n90"):
        xs, ys, yerr_lo, yerr_hi, is_bracket_list, labels = [], [], [], [], [], []
        for model, rel in RELEASE.items():
            if model not in MEASURED:
                continue
            entry = MEASURED[model][horizon]
            y, elo, ehi, is_bracket = _point_and_err(entry)
            xs.append(rel)
            ys.append(y)
            yerr_lo.append(elo)
            yerr_hi.append(ehi)
            is_bracket_list.append(is_bracket)
            labels.append(model)

        fmt = markers[horizon]
        col = colors[horizon]
        # split fitted points (real CI) from brackets (visually distinct: hollow marker, dashed cap)
        for x, y, elo, ehi, is_bracket, lab in zip(xs, ys, yerr_lo, yerr_hi, is_bracket_list, labels):
            ax.errorbar([x], [y], yerr=[[elo], [ehi]], fmt=fmt, markersize=11 if not is_bracket else 9,
                        color=col, ecolor=col, elinewidth=2 if not is_bracket else 1.3,
                        capsize=5, markerfacecolor=col if not is_bracket else "white",
                        markeredgecolor=col, markeredgewidth=1.8, zorder=3,
                        linestyle=(0, (3, 2)) if is_bracket else "solid")
            # One combined annotation per (model, horizon), offset so N50 sits
            # above its marker and N90 below -- avoids stacking both horizons'
            # text on top of each other AND on top of neighboring models.
            base_dy = label_dy.get(lab, 30)
            dy = base_dy if horizon == "n50" else -base_dy
            suffix = "(bracket)" if is_bracket else "(fit+CI)"
            ax.annotate(f"{lab} {horizon.upper()}\n~{y:,.0f} ops {suffix}",
                        (x, y), textcoords="offset points", xytext=(12, dy),
                        fontsize=7.5, color=col,
                        arrowprops=dict(arrowstyle="-", color=col, alpha=0.4, lw=0.6))

        if len(xs) >= 2:
            slope, inter = _fit_trend(xs, ys)
            trend_lines[horizon] = (slope, inter, min(xs))
            x_end = mdates.date2num(date(2029, 1, 1))
            xs_fit = [mdates.date2num(min(xs)), x_end]
            ax.plot([mdates.num2date(a) for a in xs_fit],
                    [10 ** (inter + slope * a) for a in xs_fit],
                    ls="--", color=col, alpha=0.6, zorder=2,
                    label=f"{horizon.upper()} trend (extrapolation from {len(xs)} points, mostly brackets)")

    # gpt-4o floor marker (excluded from both trends)
    ax.annotate("gpt-4o: 0% at every tested length\n(engagement/calibration floor,\nnot a length-driven decay)",
                (RELEASE["gpt-4o"], 60), fontsize=8, color="#555555",
                textcoords="offset points", xytext=(-10, 10))
    ax.plot([RELEASE["gpt-4o"]], [60], "x", color="#555555", markersize=8)

    for name, (lo, hi), col in [("full ECDSA verify", ECDSA_BAND, "#E69F00"),
                                 ("full TEE attestation check", TEE_BAND, "#009E73")]:
        ax.axhspan(lo, hi, color=col, alpha=0.15)
        ax.text(date(2024, 8, 1), (lo * hi) ** 0.5, name, fontsize=9, va="center", color=col)
        for horizon, (slope, inter, _xmin) in trend_lines.items():
            cross = (math.log10((lo * hi) ** 0.5) - inter) / slope
            print(f"{horizon.upper()} trend crosses {name}: ~{mdates.num2date(cross).date()}")

    ax.set_yscale("log")
    ax.set_ylim(20, 8_000_000)
    ax.set_xlim(date(2024, 1, 1), date(2029, 1, 1))
    ax.set_xlabel("Model release date")
    ax.set_ylabel("Trace-verification horizon (checkable operations, log)")
    ax.set_title("Trace-verification horizon over time: N50 and N90, measured\n"
                  "(MVP grid, 2026-07-12 -- honesty: mostly brackets, not fitted crossings; "
                  "extrapolation from very few points)",
                  fontsize=11, weight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.grid(True, axis="y", color="#DDDDDD", linewidth=0.8, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    out = os.path.join(HERE, "verification_horizon_measured.png")
    fig.savefig(out, dpi=150)
    print("wrote", out)


if __name__ == "__main__":
    main()
