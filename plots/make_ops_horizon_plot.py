"""Preliminary ops-horizon vs release-date plot (the METR-style trace-horizon trend).

N50 = trace length (checkable operations) at which a model's tamper-detection
reliability is 50%. These points are BACK-CALCULATED from each model's measured
detection reliability at the single measured length (448 operations, checkable
rendering, results_v2.jsonl) under reliability(N) = r448^(N/448). The
verification-frontier experiment replaces them with directly measured points.

Run: python3 make_ops_horizon_plot.py   (writes ops_horizon_vs_time.png; no API calls)
"""
import json
import math
import os
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = os.path.dirname(__file__)

def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(1e-6, c - h), min(1 - 1e-6, c + h)

def n50_from_r448(r):
    # reliability(N) = r^(N/448); solve reliability = 0.5
    return 448 * math.log(0.5) / math.log(r)

# (label, release date from the api model id, detected, n, lower_bound_flag)
MODELS = [
    ("gpt-5", date(2025, 8, 7), 22, 42, False),
    ("claude-opus-4.6", date(2026, 2, 5), 42, 42, True),   # 42/42: N50 is a lower bound
    ("gpt-5.5", date(2026, 4, 23), 37, 42, False),
]
# gpt-4o and o3 are excluded: 0/42 detection is an engagement floor, not a length effect.

xs, ys, ylo, yhi, labels, lbs = [], [], [], [], [], []
CAP = 6_000_000
for label, rel, k, n, lb in MODELS:
    k_eff = min(k, n - 0.5)  # continuity correction for 42/42
    r = k_eff / n
    r_lo, r_hi = wilson(k, n)
    r_lo = min(r_lo, r - 1e-9)          # keep bounds strictly around the point
    r_hi = min(max(r_hi, r + 1e-9), 1 - 1e-6)
    y = n50_from_r448(r)
    y_lo = n50_from_r448(r_lo)          # n50 is increasing in r
    y_hi = min(n50_from_r448(r_hi), CAP)
    xs.append(rel); ys.append(y)
    ylo.append(y - y_lo); yhi.append(y_hi - y)
    labels.append(label); lbs.append(lb)

fig, ax = plt.subplots(figsize=(9, 6))
ax.errorbar(xs, ys, yerr=[ylo, yhi], fmt="o", markersize=10, capsize=5,
            color="#0072B2", ecolor="#0072B2", elinewidth=2,
            markeredgecolor="white", markeredgewidth=1.5, zorder=3)
for x, y, lab, lb in zip(xs, ys, labels, lbs):
    txt = f"{lab}\n~{y:,.0f} ops" + (" (lower bound)" if lb else "")
    ax.annotate(txt, (x, y), textcoords="offset points", xytext=(10, 6), fontsize=10)

# log-linear trend through the estimated points, extrapolated
xo = [mdates.date2num(x) for x in xs]
ly = [math.log10(y) for y in ys]
n_ = len(xo)
sx, sy = sum(xo), sum(ly)
sxx = sum(a * a for a in xo); sxy = sum(a * b for a, b in zip(xo, ly))
slope = (n_ * sxy - sx * sy) / (n_ * sxx - sx * sx)
inter = (sy - slope * sx) / n_
x_end = mdates.date2num(date(2028, 12, 31))
xs_fit = [min(xo), x_end]
ax.plot([mdates.num2date(a) for a in xs_fit],
        [10 ** (inter + slope * a) for a in xs_fit],
        ls="--", color="#0072B2", alpha=0.6, zorder=2, label="trend (estimated points)")
double_days = math.log10(2) / slope
print(f"doubling time: {double_days:.0f} days")
for name, lo, hi, col in [("full ECDSA verify", 410_000, 800_000, "#E69F00"),
                          ("full TEE attestation check", 1_200_000, 3_200_000, "#D55E00")]:
    ax.axhspan(lo, hi, color=col, alpha=0.15)
    ax.text(date(2024, 11, 1), (lo * hi) ** 0.5, name, fontsize=9, va="center", color=col)
    cross = (math.log10((lo * hi) ** 0.5) - inter) / slope
    print(f"{name}: trend crosses ~{mdates.num2date(cross).date()}")

# No-CoT (covert) estimate: anchor from the Think Fast paper (arXiv 2606.07157) gap.
# gpt-5.5 no-CoT task horizon >3 min vs its with-CoT horizon (~150x gap), and its
# ~1,500-reasoning-token horizon at ~30 tokens/checkable line, both give a few dozen
# ops today; grown at the paper's no-CoT doubling time of 373 days.
NOCOT_ANCHOR_DATE = date(2026, 4, 23)   # gpt-5.5 release
NOCOT_ANCHOR_OPS = 25                   # central estimate; range ~15-75
x0 = mdates.date2num(NOCOT_ANCHOR_DATE)
slope_nocot = math.log10(2) / 373
x_no = [x0, mdates.date2num(date(2028, 12, 31))]
ax.plot([mdates.num2date(a) for a in x_no],
        [NOCOT_ANCHOR_OPS * 10 ** (slope_nocot * (a - x0)) for a in x_no],
        ls="-.", color="#CC79A7", alpha=0.9, zorder=2,
        label="no-CoT (covert) estimate, Think Fast gap, 373-day doubling")
ax.errorbar([NOCOT_ANCHOR_DATE], [NOCOT_ANCHOR_OPS], yerr=[[10], [50]], fmt="s",
            markersize=8, capsize=4, color="#CC79A7", markeredgecolor="white", zorder=3)
ax.annotate("gpt-5.5 covert\n~25 ops", (NOCOT_ANCHOR_DATE, NOCOT_ANCHOR_OPS),
            textcoords="offset points", xytext=(10, -18), fontsize=9, color="#CC79A7")

ax.axhline(448, color="gray", lw=1, ls=":")
ax.text(date(2024, 11, 1), 500, "measured length (448 ops, SHA-256 trace)", fontsize=8.5, color="gray")
ax.set_yscale("log")
ax.set_ylim(200, 8_000_000)
ax.set_xlim(date(2024, 10, 1), date(2029, 1, 1))
ax.set_xlabel("Model release date")
ax.set_ylabel("Estimated 50%-reliability trace length (checkable operations, log)")
ax.set_title("Trace-verification horizon over time (estimated, pending direct measurement)",
             fontsize=12, weight="bold")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.grid(True, axis="y", color="#DDDDDD", linewidth=0.8, zorder=0)
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, fontsize=9, loc="lower right")
fig.tight_layout()
out = os.path.join(HERE, "ops_horizon_vs_time.png")
fig.savefig(out, dpi=150)
print("wrote", out)
