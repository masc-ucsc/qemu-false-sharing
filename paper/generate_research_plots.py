#!/usr/bin/env python3
"""
Publication-quality research plots for QEMU False Sharing Detection Framework.
Uses IEEE/ACM-style formatting suitable for conference/journal papers.

Generates:
  1. Fig 1: Aggregate conflict overview (grouped bar)
  2. Fig 2: Per-benchmark R-W / W-W decomposition (100% stacked + absolute)
  3. Fig 3: Detection surface (cache lines × PCs) scatter
  4. Fig 4: Conflict intensity heatmap (log-normalized)
  5. Fig 5: Conflict concentration (Lorenz-style) — top cache lines account for X%
  6. Fig 6: Per-benchmark hotspot waterfall (Top-5 PCs)
  7. Fig 7: W-W ratio comparison (false sharing severity proxy)
  8. Fig 8: Multi-panel summary figure (2×3)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path
from matplotlib.gridspec import GridSpec

# ── IEEE/Research Style ──────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "Palatino", "Georgia"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 8.5,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.6,
    "axes.grid": True,
    "grid.color": "#DDDDDD",
    "grid.linewidth": 0.4,
    "grid.alpha": 0.7,
    "lines.linewidth": 1.5,
    "lines.markersize": 5,
})

OUT = Path(__file__).parent / "research_figures"
OUT.mkdir(exist_ok=True)

# ── Color Palette (colorblind-safe, print-friendly) ─────────────────────────
# Using Wong's colorblind-safe palette adapted for research figures
COLORS = {
    "parallel_compress": "#0072B2",   # Blue
    "word_count":        "#D55E00",   # Vermillion
    "parallel_sort":     "#E69F00",   # Orange
    "false_sharing":     "#009E73",   # Bluish Green
    "duckdb":            "#CC79A7",   # Reddish Purple
}
RW_COLOR = "#0072B2"
WW_COLOR = "#D55E00"

LABELS = {
    "parallel_compress": "P-Compress",
    "word_count":        "Word Count",
    "parallel_sort":     "P-Sort",
    "false_sharing":     "False Share",
    "duckdb":            "DuckDB",
}

LABELS_FULL = {
    "parallel_compress": "Parallel Compress",
    "word_count":        "Word Count",
    "parallel_sort":     "Parallel Sort",
    "false_sharing":     "False Sharing",
    "duckdb":            "DuckDB",
}

# ── Data ─────────────────────────────────────────────────────────────────────
benchmarks = {
    "parallel_compress": {"total": 17176,  "rw": 16919,  "ww": 257,    "cls": 167, "pcs": 73},
    "word_count":        {"total": 227808, "rw": 216763, "ww": 11045,  "cls": 247, "pcs": 112},
    "parallel_sort":     {"total": 208458, "rw": 180041, "ww": 28417,  "cls": 208, "pcs": 134},
    "false_sharing":     {"total": 3829,   "rw": 1789,   "ww": 2040,   "cls": 26,  "pcs": 33},
    "duckdb":            {"total": 203579, "rw": 203265, "ww": 314,    "cls": 378, "pcs": 922},
}

# Per-benchmark top hotspot PCs
hotspots = {
    "parallel_compress": [
        ("compress.c:61",   14656, "rw"),
        ("compress.c:126",  483,   "rw"),
        ("compress.c:77",   158,   "rw"),
        ("compress.c:79",   63,    "rw"),
    ],
    "word_count": [
        ("wc.c:104",        40755, "rw"),
        ("wc.c:105",        34765, "rw"),
        ("wc.c:98",         23950, "rw"),
        ("wc.c:114",        10874, "mixed"),
        ("wc.c:61",         2942,  "rw"),
    ],
    "parallel_sort": [
        ("sort.c:65",       106805,"rw"),
        ("msort.o (glibc)", 35280, "rw"),
        ("sort.c:54–55",    18648, "rw"),
        ("sort.c:100",      2046,  "rw"),
    ],
    "false_sharing": [
        ("fs.c:43",         1882, "mixed"),
        ("fs.c:51",         1893, "mixed"),
    ],
    "duckdb": [
        ("thread_pool",     110000, "rw"),
        ("task_queue",      70000,  "rw"),
        ("allocator",       9323,   "rw"),
        ("query_exec",      2342,   "rw"),
    ],
}

# Top cache lines per benchmark (for concentration analysis)
# Percentage of total conflicts in top-1, top-3, top-5, top-10, top-20 cache lines
concentration = {
    "parallel_compress": [3.7, 7.8, 12.2, 16.5, 22.1],
    "word_count":        [15.6, 32.9, 37.9, 43.6, 52.0],
    "parallel_sort":     [1.5, 4.5, 6.6, 10.2, 17.2],
    "false_sharing":     [98.7, 99.1, 99.4, 99.7, 99.9],
    "duckdb":            [88.5, 97.7, 98.1, 98.5, 99.0],
}

apps = list(benchmarks.keys())

def thousands(x, pos=None):
    if abs(x) >= 1e6: return f"{x/1e6:.1f}M"
    if abs(x) >= 1e3: return f"{x/1e3:.0f}K"
    return f"{x:.0f}"

def save(fig, name):
    for ext in ["png", "pdf"]:
        fig.savefig(OUT / f"{name}.{ext}", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 1: Aggregate Conflict Overview (Grouped Bar)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Generating Research Figures ──")

fig, ax = plt.subplots(figsize=(6.5, 3.2), facecolor="white")
ax.set_facecolor("white")

x = np.arange(len(apps))
w = 0.28

rw_vals = [benchmarks[a]["rw"] for a in apps]
ww_vals = [benchmarks[a]["ww"] for a in apps]
total_vals = [benchmarks[a]["total"] for a in apps]

bars_rw = ax.bar(x - w/2, rw_vals, w, color=RW_COLOR, label="Read–Write (R-W)",
                 edgecolor="white", linewidth=0.5, zorder=3)
bars_ww = ax.bar(x + w/2, ww_vals, w, color=WW_COLOR, label="Write–Write (W-W)",
                 edgecolor="white", linewidth=0.5, zorder=3)

# Total annotations above
for i in range(len(apps)):
    ax.text(i, total_vals[i] * 1.02, f"{total_vals[i]:,}",
            ha="center", va="bottom", fontsize=7, fontweight="bold", color="#333")

ax.set_xticks(x)
ax.set_xticklabels([LABELS[a] for a in apps], fontweight="medium")
ax.set_ylabel("Conflict Count")
ax.set_yscale("log")
ax.set_ylim(100, 5e5)
ax.legend(loc="upper left", framealpha=0.95, edgecolor="#ccc")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_title("(a) Cross-Core Cache-Line Conflicts by Benchmark", fontweight="bold")
plt.tight_layout()
save(fig, "fig1_conflict_overview")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 2: 100% Stacked Bar — R-W vs W-W Proportions
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6.5, 2.8), facecolor="white")
ax.set_facecolor("white")

rw_pct = [benchmarks[a]["rw"] / benchmarks[a]["total"] * 100 for a in apps]
ww_pct = [benchmarks[a]["ww"] / benchmarks[a]["total"] * 100 for a in apps]

y = np.arange(len(apps))
h = 0.55

ax.barh(y, rw_pct, h, color=RW_COLOR, label="R-W", edgecolor="white", linewidth=0.5, zorder=3)
ax.barh(y, ww_pct, h, left=rw_pct, color=WW_COLOR, label="W-W", edgecolor="white", linewidth=0.5, zorder=3)

for i in range(len(apps)):
    # R-W label
    if rw_pct[i] > 15:
        ax.text(rw_pct[i]/2, i, f"{rw_pct[i]:.1f}%", ha="center", va="center",
                fontsize=8, fontweight="bold", color="white")
    # W-W label
    if ww_pct[i] > 5:
        ax.text(rw_pct[i] + ww_pct[i]/2, i, f"{ww_pct[i]:.1f}%", ha="center", va="center",
                fontsize=8, fontweight="bold", color="white")
    elif ww_pct[i] > 0.1:
        ax.text(101, i, f"{ww_pct[i]:.1f}%", ha="left", va="center",
                fontsize=7, color=WW_COLOR)

ax.set_yticks(y)
ax.set_yticklabels([LABELS_FULL[a] for a in apps])
ax.set_xlabel("Proportion of Total Conflicts (%)")
ax.set_xlim(0, 108)
ax.invert_yaxis()
ax.legend(loc="lower right", framealpha=0.95, edgecolor="#ccc")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_title("(b) Conflict Type Decomposition", fontweight="bold")
plt.tight_layout()
save(fig, "fig2_conflict_decomposition")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 3: Detection Surface Scatter (Cache Lines × Unique PCs)
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(5.5, 4.5), facecolor="white")
ax.set_facecolor("white")

for a in apps:
    d = benchmarks[a]
    size = np.sqrt(d["total"]) * 2.5
    ax.scatter(d["cls"], d["pcs"], s=size, color=COLORS[a],
               alpha=0.75, edgecolors="#333", linewidth=0.8, zorder=3)

    # Offset labels to avoid overlap
    offsets = {
        "parallel_compress": (10, -15),
        "word_count":        (10, 10),
        "parallel_sort":     (10, 5),
        "false_sharing":     (10, -10),
        "duckdb":            (-60, -40),
    }
    dx, dy = offsets[a]
    ax.annotate(f"{LABELS[a]}\n({d['total']:,})",
                xy=(d["cls"], d["pcs"]),
                xytext=(d["cls"] + dx, d["pcs"] + dy),
                fontsize=7.5, color=COLORS[a], fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=COLORS[a], alpha=0.5, lw=0.8))

ax.set_xlabel("Unique Cache Lines Affected")
ax.set_ylabel("Unique Program Counters (PCs) Involved")
ax.set_title("(c) Detection Surface\n(bubble size ∝ total conflicts)", fontweight="bold")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
plt.tight_layout()
save(fig, "fig3_detection_surface")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 4: Normalized Heatmap (all metrics)
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6.5, 3.0), facecolor="white")
ax.set_facecolor("white")

metric_names = ["Total", "R-W", "W-W", "Cache\nLines", "PCs", "Conflicts\n/Line"]
data = []
for a in apps:
    d = benchmarks[a]
    data.append([d["total"], d["rw"], d["ww"], d["cls"], d["pcs"], d["total"]/d["cls"]])

data_arr = np.array(data, dtype=float)
# Log-normalize for better visual contrast
data_log = np.log10(data_arr + 1)
col_max = data_log.max(axis=0)
col_max[col_max == 0] = 1
data_norm = data_log / col_max

im = ax.imshow(data_norm, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)

for i in range(len(apps)):
    for j in range(len(metric_names)):
        val = data_arr[i, j]
        if val >= 1000:
            txt = f"{val/1000:.1f}K" if val < 1e6 else f"{val/1e6:.1f}M"
        else:
            txt = f"{val:.0f}"
        tc = "white" if data_norm[i, j] > 0.6 else "#1E293B"
        ax.text(j, i, txt, ha="center", va="center", fontsize=8, fontweight="bold", color=tc)

ax.set_xticks(range(len(metric_names)))
ax.set_xticklabels(metric_names, fontsize=8.5)
ax.set_yticks(range(len(apps)))
ax.set_yticklabels([LABELS_FULL[a] for a in apps], fontsize=9)
ax.set_title("(d) Benchmark Comparison Heatmap (log-normalized)", fontweight="bold")

cbar = plt.colorbar(im, ax=ax, shrink=0.9, pad=0.02)
cbar.set_label("Normalized Intensity", fontsize=8)
cbar.ax.tick_params(labelsize=7)
plt.tight_layout()
save(fig, "fig4_heatmap")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 5: Conflict Concentration (how many cache lines account for X%)
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6, 4), facecolor="white")
ax.set_facecolor("white")

categories = ["Top 1", "Top 3", "Top 5", "Top 10", "Top 20"]
x_cat = np.arange(len(categories))

for a in apps:
    ax.plot(x_cat, concentration[a], "o-", color=COLORS[a],
            label=LABELS[a], markersize=5, zorder=3, linewidth=1.8)

ax.axhline(y=80, color="#999", linestyle="--", linewidth=0.8, alpha=0.5)
ax.text(4.5, 81, "80% line", fontsize=7, color="#999", va="bottom")

ax.set_xticks(x_cat)
ax.set_xticklabels([f"Top-{n}" for n in [1,3,5,10,20]])
ax.set_xlabel("Number of Cache Lines (ranked by conflict count)")
ax.set_ylabel("Cumulative % of Total Conflicts")
ax.set_ylim(0, 105)
ax.legend(loc="lower right", framealpha=0.95, edgecolor="#ccc")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_title("(e) Conflict Concentration — Cache-Line Pareto Analysis", fontweight="bold")
plt.tight_layout()
save(fig, "fig5_concentration")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 6: Hotspot Waterfall (Top PCs per benchmark)
# ═══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 5, figsize=(14, 3.5), facecolor="white", sharey=False)

for idx, a in enumerate(apps):
    ax = axes[idx]
    ax.set_facecolor("white")
    hs = sorted(hotspots[a], key=lambda x: x[1], reverse=True)[:5]

    labels_hs = [h[0] for h in hs]
    vals = [h[1] for h in hs]
    types = [h[2] for h in hs]

    hs_colors = []
    for t in types:
        if t == "rw":     hs_colors.append(RW_COLOR)
        elif t == "ww":   hs_colors.append(WW_COLOR)
        else:             hs_colors.append("#E69F00")

    y_pos = np.arange(len(hs))
    bars = ax.barh(y_pos, vals, height=0.6, color=hs_colors,
                   edgecolor="white", linewidth=0.5, zorder=3)

    for i, v in enumerate(vals):
        pct = v / benchmarks[a]["total"] * 100
        ax.text(v + benchmarks[a]["total"] * 0.02, i, f"{pct:.0f}%",
                va="center", fontsize=7, color="#555")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels_hs, fontsize=7, fontfamily="monospace")
    ax.invert_yaxis()
    ax.set_title(LABELS[a], fontsize=9, fontweight="bold")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", labelsize=7)

fig.suptitle("(f) Top PC Hotspots per Benchmark (% of total conflicts)",
             fontsize=11, fontweight="bold", y=1.02)
plt.tight_layout()
save(fig, "fig6_hotspot_waterfall")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 7: W-W Ratio Comparison (false sharing severity indicator)
# ═══════════════════════════════════════════════════════════════════════════════
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 3.2), facecolor="white")

# Left: W-W ratio bar
ww_ratios = [benchmarks[a]["ww"] / benchmarks[a]["total"] * 100 for a in apps]
x = np.arange(len(apps))

bars = ax1.bar(x, ww_ratios, 0.55, color=[COLORS[a] for a in apps],
               edgecolor="white", linewidth=0.5, zorder=3)
for i, (bar, ratio) in enumerate(zip(bars, ww_ratios)):
    ax1.text(i, ratio + 1.5, f"{ratio:.1f}%", ha="center", fontsize=8,
             fontweight="bold", color=COLORS[apps[i]])

ax1.axhline(y=50, color="#999", linestyle=":", linewidth=0.8, alpha=0.5)
ax1.set_xticks(x)
ax1.set_xticklabels([LABELS[a] for a in apps], fontsize=8)
ax1.set_ylabel("W-W / Total (%)")
ax1.set_ylim(0, 60)
ax1.set_title("(g) W-W Ratio\n(higher = more contention)", fontsize=10, fontweight="bold")
ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)

# Right: Conflicts per cache line (intensity)
intensity = [benchmarks[a]["total"] / benchmarks[a]["cls"] for a in apps]
bars2 = ax2.bar(x, intensity, 0.55, color=[COLORS[a] for a in apps],
                edgecolor="white", linewidth=0.5, zorder=3)
for i, (bar, val) in enumerate(zip(bars2, intensity)):
    ax2.text(i, val + 10, f"{val:.0f}", ha="center", fontsize=8,
             fontweight="bold", color=COLORS[apps[i]])

avg_int = np.mean(intensity)
ax2.axhline(y=avg_int, color="#999", linestyle="--", linewidth=0.8, alpha=0.5)

ax2.set_xticks(x)
ax2.set_xticklabels([LABELS[a] for a in apps], fontsize=8)
ax2.set_ylabel("Conflicts / Cache Line")
ax2.set_title("(h) Conflict Intensity\n(higher = more concentrated)", fontsize=10, fontweight="bold")
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)

plt.tight_layout()
save(fig, "fig7_severity_intensity")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 8: Multi-panel Summary Figure (2×3 layout, publication composite)
# ═══════════════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(12, 8), facecolor="white")
gs = GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.35)

# ─── Panel A: Total conflicts (horizontal bar) ──────────────────────────
ax_a = fig.add_subplot(gs[0, 0])
sorted_apps = sorted(apps, key=lambda a: benchmarks[a]["total"], reverse=True)
y_pos = np.arange(len(sorted_apps))
vals = [benchmarks[a]["total"] for a in sorted_apps]
cols = [COLORS[a] for a in sorted_apps]
ax_a.barh(y_pos, vals, color=cols, height=0.55, edgecolor="white", linewidth=0.5, zorder=3)
for i, v in enumerate(vals):
    ax_a.text(v + 3000, i, f"{v:,}", va="center", fontsize=7, fontweight="bold", color="#333")
ax_a.set_yticks(y_pos)
ax_a.set_yticklabels([LABELS[a] for a in sorted_apps], fontsize=8)
ax_a.invert_yaxis()
ax_a.set_xlabel("Total Conflicts", fontsize=8)
ax_a.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
ax_a.set_title("(a) Total Conflicts", fontsize=10, fontweight="bold")
ax_a.spines["top"].set_visible(False)
ax_a.spines["right"].set_visible(False)

# ─── Panel B: R-W vs W-W stacked ────────────────────────────────────────
ax_b = fig.add_subplot(gs[0, 1])
rw = [benchmarks[a]["rw"] for a in apps]
ww = [benchmarks[a]["ww"] for a in apps]
y_b = np.arange(len(apps))
ax_b.barh(y_b, rw, 0.5, color=RW_COLOR, label="R-W", edgecolor="white", linewidth=0.5, zorder=3)
ax_b.barh(y_b, ww, 0.5, left=rw, color=WW_COLOR, label="W-W", edgecolor="white", linewidth=0.5, zorder=3)
ax_b.set_yticks(y_b)
ax_b.set_yticklabels([LABELS[a] for a in apps], fontsize=8)
ax_b.invert_yaxis()
ax_b.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
ax_b.set_xlabel("Conflicts", fontsize=8)
ax_b.legend(loc="lower right", fontsize=7, framealpha=0.9)
ax_b.set_title("(b) R-W vs W-W Split", fontsize=10, fontweight="bold")
ax_b.spines["top"].set_visible(False)
ax_b.spines["right"].set_visible(False)

# ─── Panel C: Detection surface scatter ──────────────────────────────────
ax_c = fig.add_subplot(gs[0, 2])
for a in apps:
    d = benchmarks[a]
    s = np.sqrt(d["total"]) * 1.8
    ax_c.scatter(d["cls"], d["pcs"], s=s, color=COLORS[a],
                 alpha=0.75, edgecolors="#333", linewidth=0.6, zorder=3, label=LABELS[a])
ax_c.set_xlabel("Cache Lines", fontsize=8)
ax_c.set_ylabel("Unique PCs", fontsize=8)
ax_c.legend(loc="upper left", fontsize=6, framealpha=0.9, markerscale=0.4)
ax_c.set_title("(c) Detection Surface", fontsize=10, fontweight="bold")
ax_c.spines["top"].set_visible(False)
ax_c.spines["right"].set_visible(False)

# ─── Panel D: W-W Ratio ─────────────────────────────────────────────────
ax_d = fig.add_subplot(gs[1, 0])
ww_r = [benchmarks[a]["ww"] / benchmarks[a]["total"] * 100 for a in apps]
x_d = np.arange(len(apps))
ax_d.bar(x_d, ww_r, 0.5, color=[COLORS[a] for a in apps],
         edgecolor="white", linewidth=0.5, zorder=3)
for i, r in enumerate(ww_r):
    ax_d.text(i, r + 1, f"{r:.1f}%", ha="center", fontsize=7, fontweight="bold", color=COLORS[apps[i]])
ax_d.set_xticks(x_d)
ax_d.set_xticklabels([LABELS[a] for a in apps], fontsize=7, rotation=15)
ax_d.set_ylabel("W-W Ratio (%)", fontsize=8)
ax_d.set_title("(d) W-W Severity", fontsize=10, fontweight="bold")
ax_d.spines["top"].set_visible(False)
ax_d.spines["right"].set_visible(False)

# ─── Panel E: Concentration ─────────────────────────────────────────────
ax_e = fig.add_subplot(gs[1, 1])
cats = [1, 3, 5, 10, 20]
for a in apps:
    ax_e.plot(range(len(cats)), concentration[a], "o-", color=COLORS[a],
              label=LABELS[a], markersize=4, linewidth=1.4, zorder=3)
ax_e.set_xticks(range(len(cats)))
ax_e.set_xticklabels([f"Top-{n}" for n in cats], fontsize=7)
ax_e.set_ylabel("Cumulative %", fontsize=8)
ax_e.set_ylim(0, 105)
ax_e.legend(loc="lower right", fontsize=6, framealpha=0.9)
ax_e.set_title("(e) Cache-Line Concentration", fontsize=10, fontweight="bold")
ax_e.spines["top"].set_visible(False)
ax_e.spines["right"].set_visible(False)

# ─── Panel F: Conflicts per cache line ───────────────────────────────────
ax_f = fig.add_subplot(gs[1, 2])
intensity_f = [benchmarks[a]["total"] / benchmarks[a]["cls"] for a in apps]
x_f = np.arange(len(apps))
ax_f.bar(x_f, intensity_f, 0.5, color=[COLORS[a] for a in apps],
         edgecolor="white", linewidth=0.5, zorder=3)
for i, v in enumerate(intensity_f):
    ax_f.text(i, v + 10, f"{v:.0f}", ha="center", fontsize=7, fontweight="bold", color=COLORS[apps[i]])
ax_f.set_xticks(x_f)
ax_f.set_xticklabels([LABELS[a] for a in apps], fontsize=7, rotation=15)
ax_f.set_ylabel("Conflicts / Line", fontsize=8)
ax_f.set_title("(f) Conflict Intensity", fontsize=10, fontweight="bold")
ax_f.spines["top"].set_visible(False)
ax_f.spines["right"].set_visible(False)

fig.suptitle("QEMU False Sharing Detection — Evaluation Summary",
             fontsize=13, fontweight="bold", y=1.01)
plt.tight_layout()
save(fig, "fig8_summary_composite")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 9: Benchmark Characteristics Table (visual)
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 2.5), facecolor="white")
ax.axis("off")

table_data = []
for a in apps:
    d = benchmarks[a]
    table_data.append([
        LABELS_FULL[a],
        f"{d['total']:,}",
        f"{d['rw']:,}",
        f"{d['ww']:,}",
        f"{d['ww']/d['total']*100:.1f}%",
        str(d['cls']),
        str(d['pcs']),
        f"{d['total']/d['cls']:.0f}",
    ])

col_labels = ["Benchmark", "Total", "R-W", "W-W", "W-W%", "CL", "PCs", "Conf/CL"]
table = ax.table(cellText=table_data, colLabels=col_labels,
                 cellLoc="center", loc="center")
table.auto_set_font_size(False)
table.set_fontsize(8)
table.scale(1.0, 1.5)

# Style header
for j in range(len(col_labels)):
    table[0, j].set_facecolor("#2C3E50")
    table[0, j].set_text_props(color="white", fontweight="bold")
    table[0, j].set_edgecolor("white")

# Alternate row colors
for i in range(1, len(apps) + 1):
    color = "#F8F9FA" if i % 2 == 0 else "white"
    for j in range(len(col_labels)):
        table[i, j].set_facecolor(color)
        table[i, j].set_edgecolor("#DEE2E6")

ax.set_title("Table 1: Summary of Detection Results Across All Benchmarks",
             fontsize=10, fontweight="bold", pad=12)
plt.tight_layout()
save(fig, "table1_results_summary")

print(f"\n✅ All research figures saved to {OUT}/")
print(f"   Figures: 9 (PNG + PDF)")
