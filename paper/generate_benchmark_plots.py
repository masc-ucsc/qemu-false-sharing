#!/usr/bin/env python3
"""
World-class benchmark visualization suite for QEMU False Sharing Detection.
Generates individual + combined plots for 5 benchmarks.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import seaborn as sns
from pathlib import Path
from matplotlib.gridspec import GridSpec
from matplotlib import colormaps

# ── Global Style ─────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 200, "savefig.dpi": 300,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "axes.edgecolor": "#334155",
    "axes.linewidth": 0.8,
    "grid.color": "#E2E8F0",
    "grid.linewidth": 0.5,
    "xtick.color": "#475569",
    "ytick.color": "#475569",
    "text.color": "#1E293B",
})

BG = "#FAFBFC"
DARK_BG = "#0F172A"
CARD_BG = "#1E293B"

# Curated palette
C = {
    "blue":    "#2563EB",
    "red":     "#DC2626",
    "green":   "#059669",
    "amber":   "#D97706",
    "purple":  "#7C3AED",
    "cyan":    "#0891B2",
    "pink":    "#DB2777",
    "slate":   "#64748B",
    "indigo":  "#4F46E5",
    "emerald": "#10B981",
}

APP_COLORS = {
    "parallel_compress": C["blue"],
    "word_count":        C["red"],
    "parallel_sort":     C["amber"],
    "false_sharing":     C["green"],
    "duckdb":            C["purple"],
}

APP_LABELS = {
    "parallel_compress": "Parallel Compress",
    "word_count":        "Word Count",
    "parallel_sort":     "Parallel Sort",
    "false_sharing":     "False Sharing",
    "duckdb":            "DuckDB v1.2.1",
}

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)

# ── Data ─────────────────────────────────────────────────────────────────────
benchmarks = {
    "parallel_compress": {"total": 17176, "rw": 16919, "ww": 257,   "cls": 167, "pcs": 73},
    "word_count":        {"total": 227808,"rw": 216763,"ww": 11045, "cls": 247, "pcs": 112},
    "parallel_sort":     {"total": 208458,"rw": 180041,"ww": 28417, "cls": 208, "pcs": 134},
    "false_sharing":     {"total": 3829,  "rw": 1789,  "ww": 2040,  "cls": 26,  "pcs": 33},
    "duckdb":            {"total": 203579,"rw": 203265,"ww": 314,   "cls": 378, "pcs": 922},
}

# Per-benchmark hotspot data
hotspots = {
    "parallel_compress": [
        ("compress.c:61\nCRC32 block", 14656, "rw"),
        ("compress.c:126\nwriter poll", 483, "rw"),
        ("compress.c:77\nqueue scan", 158, "rw"),
    ],
    "word_count": [
        ("wc.c:104\ntolower()", 81500, "rw"),
        ("wc.c:105\nword accum", 34765, "rw"),
        ("wc.c:98\nwhitespace", 23950, "rw"),
        ("wc.c:114\nstats[tid]++", 10874, "mixed"),
        ("wc.c:61\nht_insert()", 2942, "rw"),
    ],
    "parallel_sort": [
        ("sort.c:65\nmerge loop", 106805, "rw"),
        ("sort.c:54-55\ncmp_u64()", 18648, "rw"),
        ("msort.o\nglibc merge", 9371, "rw"),
        ("sort.c:100\nis_sorted()", 2046, "rw"),
    ],
    "false_sharing": [
        ("fs.c:43\ncounters[0]++", 1882, "mixed"),
        ("fs.c:51\ncounters[1]++", 1893, "mixed"),
    ],
    "duckdb": [
        ("0x3fc718\nthread pool", 110000, "rw"),
        ("0x3fcad8\ntask queue", 70000, "rw"),
        ("0x13f830c\nallocator", 9323, "rw"),
    ],
}

def thousands(x, pos=None):
    if x >= 1000:
        return f"{x/1000:.0f}K"
    return f"{x:.0f}"

def save(fig, name):
    fig.savefig(OUT / name, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ {name}")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 1: Total Conflicts Bar (main comparison)
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=BG)
ax.set_facecolor(BG)

apps = list(benchmarks.keys())
totals = [benchmarks[a]["total"] for a in apps]
colors = [APP_COLORS[a] for a in apps]
labels = [APP_LABELS[a] for a in apps]

bars = ax.barh(range(len(apps)), totals, color=colors, height=0.6,
               edgecolor="white", linewidth=1.5, zorder=3)

for i, (bar, total) in enumerate(zip(bars, totals)):
    ax.text(bar.get_width() + 3000, i, f"{total:,}",
            va="center", ha="left", fontsize=11, fontweight="bold", color=colors[i])

ax.set_yticks(range(len(apps)))
ax.set_yticklabels(labels, fontsize=12, fontweight="medium")
ax.invert_yaxis()
ax.set_xlabel("Total Cross-Core Conflicts Detected", fontsize=12, fontweight="medium")
ax.set_title("False Sharing Detection Across All Benchmarks",
             fontsize=15, fontweight="bold", pad=14, color="#0F172A")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_xlim(0, max(totals) * 1.18)

# Grand total annotation
gt = sum(totals)
ax.text(0.98, 0.02, f"Total: {gt:,} conflicts", transform=ax.transAxes,
        ha="right", va="bottom", fontsize=11, fontweight="bold", color=C["slate"],
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#E2E8F0", alpha=0.9))

plt.tight_layout()
save(fig, "combined_total_conflicts.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 2: R-W vs W-W Stacked Bar
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=BG)
ax.set_facecolor(BG)

rw = [benchmarks[a]["rw"] for a in apps]
ww = [benchmarks[a]["ww"] for a in apps]
y = np.arange(len(apps))

bars_rw = ax.barh(y, rw, height=0.55, color=C["blue"], label="Read–Write", 
                  edgecolor="white", linewidth=1, zorder=3)
bars_ww = ax.barh(y, ww, height=0.55, left=rw, color=C["red"], label="Write–Write",
                  edgecolor="white", linewidth=1, zorder=3)

for i in range(len(apps)):
    total = rw[i] + ww[i]
    rw_pct = rw[i] / total * 100
    ww_pct = ww[i] / total * 100
    if rw[i] > total * 0.15:
        ax.text(rw[i] * 0.5, i, f"{rw_pct:.0f}%", va="center", ha="center",
                fontsize=9, fontweight="bold", color="white")
    if ww[i] > total * 0.08:
        ax.text(rw[i] + ww[i] * 0.5, i, f"{ww_pct:.0f}%", va="center", ha="center",
                fontsize=9 if ww_pct > 5 else 7, fontweight="bold", color="white")
    ax.text(total + 2000, i, f"{total:,}", va="center", ha="left",
            fontsize=9, color=C["slate"])

ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=11)
ax.invert_yaxis()
ax.set_xlabel("Conflict Count", fontsize=11)
ax.set_title("Conflict Composition — Read-Write vs Write-Write",
             fontsize=14, fontweight="bold", pad=14)
ax.legend(loc="lower right", fontsize=10, framealpha=0.95)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.set_xlim(0, max(rw[i]+ww[i] for i in range(len(apps))) * 1.15)
plt.tight_layout()
save(fig, "combined_rw_ww_stacked.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 3: Cache Lines vs PCs Scatter (Bubble)
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 7), facecolor=BG)
ax.set_facecolor(BG)

for a in apps:
    d = benchmarks[a]
    size = np.sqrt(d["total"]) * 1.8
    ax.scatter(d["cls"], d["pcs"], s=size**2 / 50, color=APP_COLORS[a],
               alpha=0.7, edgecolors="white", linewidth=2, zorder=3, label=APP_LABELS[a])
    offset_x = 8 if a != "false_sharing" else -15
    offset_y = 15 if a != "duckdb" else -30
    ax.annotate(f"{APP_LABELS[a]}\n{d['total']:,}",
                xy=(d["cls"], d["pcs"]),
                xytext=(d["cls"] + offset_x, d["pcs"] + offset_y),
                fontsize=9, fontweight="bold", color=APP_COLORS[a],
                arrowprops=dict(arrowstyle="-", color=APP_COLORS[a], alpha=0.4, lw=1),
                ha="left", va="bottom")

ax.set_xlabel("Unique Cache Lines Affected", fontsize=12, fontweight="medium")
ax.set_ylabel("Unique PCs Involved", fontsize=12, fontweight="medium")
ax.set_title("Detection Surface — Cache Lines vs Program Counters\n(bubble size ∝ total conflicts)",
             fontsize=14, fontweight="bold", pad=14)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(True, alpha=0.3)
plt.tight_layout()
save(fig, "combined_scatter_bubble.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 4: Multi-metric Radar
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True), facecolor=BG)

categories = ["Total\nConflicts", "R-W\nConflicts", "W-W\nConflicts",
              "Cache Lines\nAffected", "Unique\nPCs"]
N = len(categories)
angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
angles += angles[:1]

# Normalize each metric to 0-10 scale
maxvals = {
    "total": max(d["total"] for d in benchmarks.values()),
    "rw": max(d["rw"] for d in benchmarks.values()),
    "ww": max(d["ww"] for d in benchmarks.values()),
    "cls": max(d["cls"] for d in benchmarks.values()),
    "pcs": max(d["pcs"] for d in benchmarks.values()),
}

for a in apps:
    d = benchmarks[a]
    scores = [
        d["total"] / maxvals["total"] * 10,
        d["rw"] / maxvals["rw"] * 10,
        d["ww"] / maxvals["ww"] * 10,
        d["cls"] / maxvals["cls"] * 10,
        d["pcs"] / maxvals["pcs"] * 10,
    ]
    scores += scores[:1]
    ax.plot(angles, scores, "o-", linewidth=2.2, label=APP_LABELS[a],
            color=APP_COLORS[a], markersize=5, zorder=3)
    ax.fill(angles, scores, alpha=0.06, color=APP_COLORS[a])

ax.set_xticks(angles[:-1])
ax.set_xticklabels(categories, fontsize=9.5)
ax.set_ylim(0, 11)
ax.set_yticks([2, 4, 6, 8, 10])
ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=7, color=C["slate"])
ax.set_title("Multi-Dimensional Benchmark Comparison",
             fontsize=14, fontweight="bold", y=1.08)
ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9, framealpha=0.95)
plt.tight_layout()
save(fig, "combined_radar.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 5: W-W Ratio Analysis (shows false sharing "severity")
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 5), facecolor=BG)
ax.set_facecolor(BG)

ww_ratios = [benchmarks[a]["ww"] / benchmarks[a]["total"] * 100 for a in apps]
rw_ratios = [100 - r for r in ww_ratios]

x = np.arange(len(apps))
w = 0.5
bars = ax.bar(x, ww_ratios, w, color=[APP_COLORS[a] for a in apps],
              edgecolor="white", linewidth=1.5, zorder=3)

for i, (bar, ratio) in enumerate(zip(bars, ww_ratios)):
    ax.text(i, ratio + 1.5, f"{ratio:.1f}%", ha="center", va="bottom",
            fontsize=11, fontweight="bold", color=APP_COLORS[apps[i]])
    ax.text(i, -3, f"{benchmarks[apps[i]]['ww']:,}\nW-W", ha="center", va="top",
            fontsize=8, color=C["slate"])

ax.axhline(y=50, color=C["red"], linewidth=1, linestyle="--", alpha=0.3, zorder=1)
ax.text(len(apps) - 0.5, 51, "50% threshold", fontsize=8, color=C["red"], alpha=0.5, va="bottom")

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylabel("Write-Write Ratio (%)", fontsize=11)
ax.set_title("Write-Write Conflict Severity — Higher Means More Contention",
             fontsize=14, fontweight="bold", pad=14)
ax.set_ylim(-8, 60)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
plt.tight_layout()
save(fig, "combined_ww_severity.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 6: Dark-mode Dashboard (all metrics at a glance)
# ═════════════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(16, 9), facecolor=DARK_BG)
gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

# Panel 1: Total conflicts treemap-style
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor(CARD_BG)
sorted_apps = sorted(apps, key=lambda a: benchmarks[a]["total"], reverse=True)
y_pos = np.arange(len(sorted_apps))
vals = [benchmarks[a]["total"] for a in sorted_apps]
cols = [APP_COLORS[a] for a in sorted_apps]
ax1.barh(y_pos, vals, color=cols, height=0.6, edgecolor=CARD_BG, linewidth=1, zorder=3)
for i, v in enumerate(vals):
    ax1.text(v + 2000, i, f"{v:,}", va="center", fontsize=8, color="white", fontweight="bold")
ax1.set_yticks(y_pos)
ax1.set_yticklabels([APP_LABELS[a] for a in sorted_apps], fontsize=8, color="#94A3B8")
ax1.invert_yaxis()
ax1.set_title("Total Conflicts", fontsize=11, fontweight="bold", color="white", pad=8)
ax1.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
ax1.tick_params(colors="#64748B")
ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)
ax1.spines["bottom"].set_color("#334155")
ax1.spines["left"].set_color("#334155")

# Panel 2: R-W / W-W split donut
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor(CARD_BG)
total_rw = sum(benchmarks[a]["rw"] for a in apps)
total_ww = sum(benchmarks[a]["ww"] for a in apps)
wedges, _, autotexts = ax2.pie(
    [total_rw, total_ww], labels=None, autopct="%1.1f%%",
    colors=[C["blue"], C["red"]],
    wedgeprops=dict(width=0.4, edgecolor=CARD_BG, linewidth=2),
    startangle=90, pctdistance=0.78
)
for t in autotexts:
    t.set_color("white")
    t.set_fontweight("bold")
    t.set_fontsize(10)
ax2.text(0, 0, f"{total_rw + total_ww:,}\ntotal", ha="center", va="center",
         fontsize=14, fontweight="bold", color="white")
ax2.set_title("R-W vs W-W Split", fontsize=11, fontweight="bold", color="white", pad=8)
rw_legend = mpatches.Patch(color=C["blue"], label=f"R-W: {total_rw:,}")
ww_legend = mpatches.Patch(color=C["red"], label=f"W-W: {total_ww:,}")
ax2.legend(handles=[rw_legend, ww_legend], loc="lower center", fontsize=8,
           facecolor=CARD_BG, edgecolor="#334155", labelcolor="white")

# Panel 3: Cache lines vs PCs (mini scatter)
ax3 = fig.add_subplot(gs[0, 2])
ax3.set_facecolor(CARD_BG)
for a in apps:
    d = benchmarks[a]
    s = np.sqrt(d["total"]) * 0.6
    ax3.scatter(d["cls"], d["pcs"], s=s**2/8, color=APP_COLORS[a],
                alpha=0.85, edgecolors="white", linewidth=1, zorder=3)
    ax3.text(d["cls"] + 5, d["pcs"] + 10, APP_LABELS[a][:8],
             fontsize=7, color=APP_COLORS[a], fontweight="bold")
ax3.set_xlabel("Cache Lines", fontsize=8, color="#94A3B8")
ax3.set_ylabel("Unique PCs", fontsize=8, color="#94A3B8")
ax3.set_title("Detection Surface", fontsize=11, fontweight="bold", color="white", pad=8)
ax3.tick_params(colors="#64748B", labelsize=7)
ax3.spines["top"].set_visible(False)
ax3.spines["right"].set_visible(False)
ax3.spines["bottom"].set_color("#334155")
ax3.spines["left"].set_color("#334155")
ax3.grid(True, color="#334155", alpha=0.5)

# Panel 4: Per-app conflict intensity (log scale)
ax4 = fig.add_subplot(gs[1, 0])
ax4.set_facecolor(CARD_BG)
intensity = [benchmarks[a]["total"] / benchmarks[a]["cls"] for a in apps]
bars4 = ax4.bar(range(len(apps)), intensity, color=[APP_COLORS[a] for a in apps],
                width=0.55, edgecolor=CARD_BG, linewidth=1, zorder=3)
for i, (bar, val) in enumerate(zip(bars4, intensity)):
    ax4.text(i, val + 20, f"{val:.0f}", ha="center", fontsize=8, color="white", fontweight="bold")
ax4.set_xticks(range(len(apps)))
ax4.set_xticklabels([APP_LABELS[a][:6] for a in apps], fontsize=7, color="#94A3B8", rotation=15)
ax4.set_title("Conflicts per Cache Line", fontsize=11, fontweight="bold", color="white", pad=8)
ax4.tick_params(colors="#64748B", labelsize=7)
ax4.spines["top"].set_visible(False)
ax4.spines["right"].set_visible(False)
ax4.spines["bottom"].set_color("#334155")
ax4.spines["left"].set_color("#334155")

# Panel 5: Top hotspot from each benchmark
ax5 = fig.add_subplot(gs[1, 1:])
ax5.set_facecolor(CARD_BG)
top_spots = []
for a in apps:
    hs = hotspots[a]
    top = hs[0]
    top_spots.append((APP_LABELS[a], top[0].split("\n")[0], top[1], APP_COLORS[a]))

top_spots.sort(key=lambda x: x[2], reverse=True)
y5 = np.arange(len(top_spots))
vals5 = [t[2] for t in top_spots]
cols5 = [t[3] for t in top_spots]
lbls5 = [f"{t[0]}: {t[1]}" for t in top_spots]

ax5.barh(y5, vals5, color=cols5, height=0.55, edgecolor=CARD_BG, linewidth=1, zorder=3)
for i, v in enumerate(vals5):
    ax5.text(v + 1500, i, f"{v:,}", va="center", fontsize=9, color="white", fontweight="bold")
ax5.set_yticks(y5)
ax5.set_yticklabels(lbls5, fontsize=8, color="#CBD5E1", fontfamily="monospace")
ax5.invert_yaxis()
ax5.set_title("#1 Hotspot per Benchmark", fontsize=11, fontweight="bold", color="white", pad=8)
ax5.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
ax5.tick_params(colors="#64748B")
ax5.spines["top"].set_visible(False)
ax5.spines["right"].set_visible(False)
ax5.spines["bottom"].set_color("#334155")
ax5.spines["left"].set_color("#334155")

fig.suptitle("QEMU False Sharing Detection — Benchmark Dashboard",
             fontsize=16, fontweight="bold", color="white", y=0.98)
save(fig, "combined_dashboard_dark.png")


# ═════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL PLOTS — One per benchmark
# ═════════════════════════════════════════════════════════════════════════════

for app_key in apps:
    d = benchmarks[app_key]
    hs = hotspots[app_key]
    color = APP_COLORS[app_key]
    label = APP_LABELS[app_key]

    fig = plt.figure(figsize=(14, 6), facecolor=BG)
    gs = GridSpec(1, 3, figure=fig, wspace=0.35, width_ratios=[1.4, 1, 0.8])

    # ─── Left: Hotspot lollipop ──────────────────────────────────────────
    ax_left = fig.add_subplot(gs[0])
    ax_left.set_facecolor(BG)

    hs_sorted = sorted(hs, key=lambda x: x[1], reverse=True)
    hs_labels = [h[0] for h in hs_sorted]
    hs_vals = [h[1] for h in hs_sorted]
    hs_types = [h[2] for h in hs_sorted]

    y_hs = np.arange(len(hs_sorted))
    hs_colors = []
    for t in hs_types:
        if t == "rw": hs_colors.append(C["blue"])
        elif t == "ww": hs_colors.append(C["red"])
        else: hs_colors.append(C["amber"])

    ax_left.hlines(y_hs, 0, hs_vals, color=hs_colors, alpha=0.45, linewidth=3, zorder=2)
    ax_left.scatter(hs_vals, y_hs, color=hs_colors, s=100, zorder=3,
                    edgecolors="white", linewidth=1.5)

    for i, (val, lbl) in enumerate(zip(hs_vals, hs_labels)):
        pct = val / d["total"] * 100
        ax_left.text(val + d["total"] * 0.02, i, f"{val:,} ({pct:.0f}%)",
                     va="center", fontsize=9, fontweight="bold", color=hs_colors[i])

    ax_left.set_yticks(y_hs)
    ax_left.set_yticklabels(hs_labels, fontsize=8, fontfamily="monospace")
    ax_left.invert_yaxis()
    ax_left.set_xlabel("Conflicts", fontsize=10)
    ax_left.set_title("Hot-Spot Analysis", fontsize=12, fontweight="bold", pad=10)
    ax_left.spines["top"].set_visible(False)
    ax_left.spines["right"].set_visible(False)
    ax_left.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))

    rw_p = mpatches.Patch(color=C["blue"], label="Read-Write")
    ww_p = mpatches.Patch(color=C["red"], label="Write-Write")
    mx_p = mpatches.Patch(color=C["amber"], label="Mixed R-W + W-W")
    handles = [rw_p]
    if any(t == "ww" for t in hs_types): handles.append(ww_p)
    if any(t == "mixed" for t in hs_types): handles.append(mx_p)
    ax_left.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.9)

    # ─── Middle: R-W vs W-W donut ────────────────────────────────────────
    ax_mid = fig.add_subplot(gs[1])
    ax_mid.set_facecolor(BG)

    sizes_d = [d["rw"], d["ww"]]
    wedges_d, _, auto_d = ax_mid.pie(
        sizes_d, autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
        colors=[C["blue"], C["red"]],
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
        startangle=90, pctdistance=0.76
    )
    for t in auto_d:
        t.set_fontsize(10)
        t.set_fontweight("bold")
        t.set_color("white")

    ax_mid.text(0, 0, f"{d['total']:,}\ntotal", ha="center", va="center",
                fontsize=15, fontweight="bold", color="#1E293B")
    ax_mid.set_title("R-W vs W-W", fontsize=12, fontweight="bold", pad=10)

    rw_l = mpatches.Patch(color=C["blue"], label=f"R-W: {d['rw']:,}")
    ww_l = mpatches.Patch(color=C["red"], label=f"W-W: {d['ww']:,}")
    ax_mid.legend(handles=[rw_l, ww_l], loc="lower center", fontsize=9, framealpha=0.9)

    # ─── Right: Key metrics cards ────────────────────────────────────────
    ax_right = fig.add_subplot(gs[2])
    ax_right.set_facecolor(BG)
    ax_right.axis("off")

    metrics = [
        ("Total Conflicts", f"{d['total']:,}", color),
        ("Cache Lines", f"{d['cls']}", C["cyan"]),
        ("Unique PCs", f"{d['pcs']}", C["indigo"]),
        ("Conflicts/Line", f"{d['total']/d['cls']:.0f}", C["amber"]),
    ]

    for j, (m_label, m_val, m_color) in enumerate(metrics):
        y_card = 0.85 - j * 0.23
        ax_right.text(0.5, y_card, m_val, transform=ax_right.transAxes,
                      ha="center", va="center", fontsize=22, fontweight="bold", color=m_color)
        ax_right.text(0.5, y_card - 0.07, m_label, transform=ax_right.transAxes,
                      ha="center", va="center", fontsize=9, color=C["slate"])

    fig.suptitle(f"{label} — False Sharing Analysis",
                 fontsize=15, fontweight="bold", color="#0F172A", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, f"individual_{app_key}.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 7: Conflict Density Heatmap (normalized)
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 4.5), facecolor=BG)
ax.set_facecolor(BG)

metrics_names = ["Total\nConflicts", "R-W", "W-W", "Cache\nLines", "PCs", "Conflicts\n/Line"]
data_matrix = []
for a in apps:
    d = benchmarks[a]
    row = [d["total"], d["rw"], d["ww"], d["cls"], d["pcs"], d["total"]/d["cls"]]
    data_matrix.append(row)

data_arr = np.array(data_matrix, dtype=float)
# Normalize each column to 0-1
col_max = data_arr.max(axis=0)
col_max[col_max == 0] = 1
data_norm = data_arr / col_max

im = ax.imshow(data_norm, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)

# Annotate with actual values
for i in range(len(apps)):
    for j in range(len(metrics_names)):
        val = data_arr[i, j]
        txt = f"{val:,.0f}"
        text_color = "white" if data_norm[i, j] > 0.55 else "#1E293B"
        ax.text(j, i, txt, ha="center", va="center", fontsize=9,
                fontweight="bold", color=text_color)

ax.set_xticks(range(len(metrics_names)))
ax.set_xticklabels(metrics_names, fontsize=10)
ax.set_yticks(range(len(apps)))
ax.set_yticklabels(labels, fontsize=11)
ax.set_title("Benchmark Comparison Heatmap — Normalized Intensity",
             fontsize=14, fontweight="bold", pad=14)

cbar = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
cbar.set_label("Relative Intensity (0–1)", fontsize=9)
plt.tight_layout()
save(fig, "combined_heatmap.png")


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED 8: Conflict Density (conflicts per cache line) ranked
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 5), facecolor=BG)
ax.set_facecolor(BG)

density = [(a, benchmarks[a]["total"] / benchmarks[a]["cls"]) for a in apps]
density.sort(key=lambda x: x[1], reverse=True)

x_d = np.arange(len(density))
vals_d = [d[1] for d in density]
cols_d = [APP_COLORS[d[0]] for d in density]
lbls_d = [APP_LABELS[d[0]] for d in density]

bars_d = ax.bar(x_d, vals_d, color=cols_d, width=0.55,
                edgecolor="white", linewidth=1.5, zorder=3)

for i, (bar, val) in enumerate(zip(bars_d, vals_d)):
    ax.text(i, val + 15, f"{val:.0f}", ha="center", fontsize=12,
            fontweight="bold", color=cols_d[i])

avg = np.mean(vals_d)
ax.axhline(y=avg, color=C["slate"], linestyle="--", linewidth=1, alpha=0.5, zorder=1)
ax.text(len(density) - 0.5, avg + 10, f"avg: {avg:.0f}", fontsize=9, color=C["slate"])

ax.set_xticks(x_d)
ax.set_xticklabels(lbls_d, fontsize=11, fontweight="medium")
ax.set_ylabel("Avg Conflicts per Cache Line", fontsize=11)
ax.set_title("Conflict Density — How Concentrated Is the False Sharing?",
             fontsize=14, fontweight="bold", pad=14)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
plt.tight_layout()
save(fig, "combined_density_ranked.png")


print(f"\n✅ All plots saved to {OUT}/")
print(f"   Individual: {len(apps)} benchmark plots")
print(f"   Combined:   8 comparison plots")
print(f"   Total:      {len(apps) + 8} figures")
