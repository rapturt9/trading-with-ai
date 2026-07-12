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
    # points: list of (horizon, tp_pct, name). Lower horizon + higher tp_pct is better.
    pts = sorted(points, key=lambda p: p[0])
    frontier, best_tp = [], -1.0
    for h, tp, name in pts:
        if tp >= best_tp:
            frontier.append((h, tp, name))
            best_tp = tp
    return frontier

points = []
for name, (h, est, hits, n) in DATA.items():
    tp_pct = 100 * hits / n
    se = 100 * math.sqrt((hits / n) * (1 - hits / n) / n)
    points.append((h, tp_pct, name, est, se))

frontier = pareto_frontier([(h, tp, name) for h, tp, name, est, se in points])
frontier_names = {name for _, _, name in frontier}

fig, ax = plt.subplots(figsize=(9, 6))

for h, tp, name, est, se in points:
    marker = "^" if est else "o"
    on_frontier = name in frontier_names
    color = "#1f77b4" if on_frontier else "#999999"
    ax.errorbar(h, tp, yerr=1.96 * se, fmt=marker, color=color, markersize=11,
                capsize=4, zorder=3)
    label = f"{name}\n({tp:.1f}%)" + (" est." if est else "")
    ax.annotate(label, (h, tp), textcoords="offset points", xytext=(10, 8), fontsize=9)

fx = [h for h, tp, name in frontier]
fy = [tp for h, tp, name in frontier]
ax.plot(fx, fy, "--", color="#1f77b4", linewidth=2, zorder=2, label="frontier (best detection achieved up to each horizon)")

dominated = [(h, tp) for h, tp, name, est, se in points if name not in frontier_names]
for h, tp in dominated:
    ax.scatter([h], [tp], marker="x", s=140, color="#d62728", zorder=4)

ax.set_xscale("log")
ticks = sorted({h for h, tp, name, est, se in points})
ax.set_xticks(ticks)
ax.get_xaxis().set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
ax.set_xticklabels([f"{int(v)}" for v in ticks], rotation=40, ha="right")
ax.set_xlabel("METR 50%-time-horizon, minutes (log scale; triangles = ECI-estimated)")
ax.set_ylabel("Tamper caught, exact round named (%, higher is better)")
ax.set_ylim(-2, 25)
ax.legend(loc="upper left", fontsize=9)
ax.set_title("Raw trace: detection vs task-length horizon,\nrising along the frontier but not monotonic in capability")
ax.grid(alpha=0.3)

fig.subplots_adjust(bottom=0.30)
fig.text(0.5, 0.01,
          "Red X = dominated (another model reaches equal-or-better detection at a lower horizon). n=42 tampered traces/model, 95% CI. gpt-5.5's horizon is ECI-estimated, not measured.",
          ha="center", fontsize=8, wrap=True)

out = "/home/ram/obsidian/experiments/260706-credible-deals-polish/rq3-replication/plots/tp_r4r_vs_horizon_pareto.png"
fig.savefig(out, dpi=150)
print(f"wrote {out}")
print("Pareto-optimal:", [n for _, _, n in frontier])
print("Dominated:", [name for h, tp, name, est, se in points if name not in frontier_names])
