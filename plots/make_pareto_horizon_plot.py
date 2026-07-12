"""
Regenerates plots/tp_r4r_vs_horizon_pareto.png -- METR time horizon vs tamper
detection, with the Pareto frontier (lower horizon + higher detection is
better) drawn as a trend curve over the raw scatter, so the underlying trend
is visible despite the non-monotonic raw points (see tp_r4r_vs_horizon.png).

Data source: README.md "Mapped to capability" table (rq3-replication,
Phase 1b max-effort results, n=42 per model). Run directly:
    python3 plots/make_pareto_horizon_plot.py
"""
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# model: (horizon_minutes, is_estimated, tp_r4r_hits, n)
DATA = {
    "gpt-4o":            (7,   False, 0,  42),
    "o3":                (120, False, 1,  42),
    "gpt-5":             (203, False, 0,  42),
    "claude-opus-4.6":   (719, False, 8,  42),
    "gpt-5.5":           (993, True,  5,  42),
}

def pareto_frontier(points):
    pts = sorted(points, key=lambda p: p[0])
    frontier, best_tp = [], -1.0
    for h, tp, name in pts:
        if tp > best_tp:
            frontier.append((h, tp, name)); best_tp = tp
    return frontier

import numpy as np
points = []
for name, (h, est, k, n) in DATA.items():
    points.append((h, 100.0 * k / n, name))
frontier = pareto_frontier(points)
dominated = [p for p in points if p not in frontier]

fig, ax = plt.subplots(figsize=(8, 5.2))
fx = [h for h, tp, _ in frontier]
fy = [tp for _, tp, _ in frontier]
# smooth fitted curve through the frontier points (quadratic in log10 horizon)
lx = np.log10(fx)
coef = np.polyfit(lx, fy, 2)
xs = np.logspace(np.log10(min(fx)), np.log10(max(fx)), 200)
ys = np.polyval(coef, np.log10(xs))
ax.plot(xs, np.clip(ys, 0, None), "--", color="#0072B2", linewidth=2, zorder=2,
        label="fitted trend through the frontier points")
for h, tp, name in frontier:
    est = DATA[name][1]
    ax.plot([h], [tp], "o", markersize=11, color="#0072B2",
            markeredgecolor="white", markeredgewidth=1.5, zorder=3)
    ax.annotate(f"{name}\n{tp:.1f}%" + (" est." if est else ""), (h, tp),
                textcoords="offset points", xytext=(10, 8), fontsize=10)
ax.set_xscale("log")
ticks = [7, 30, 120, 719]
ax.set_xticks(ticks)
ax.set_xticklabels([f"{int(v)}" for v in ticks])
ax.set_xlabel("METR 50%-time-horizon, minutes (log scale)")
ax.set_ylabel("Tamper caught, exact round named (%, higher is better)")
ax.set_ylim(-2, 26)
ax.set_title("Raw trace: detection vs task-length horizon, frontier models",
             fontsize=12, weight="bold")
ax.grid(True, axis="y", color="#DDDDDD", linewidth=0.8, zorder=0)
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, fontsize=9, loc="upper left")
fig.tight_layout()
out = "/home/ram/obsidian/experiments/260706-credible-deals-polish/rq3-replication/plots/tp_r4r_vs_horizon_pareto.png"
fig.savefig(out, dpi=150)
print("wrote", out)
print("frontier:", [n for _, _, n in frontier], "| dropped per Ram:", [n for _, _, n in dominated])
