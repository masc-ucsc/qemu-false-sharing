#!/usr/bin/env python3
"""
Per-benchmark detailed research plots.
Parses actual report files from results/ to produce data-driven figures.

For each benchmark generates:
  (a) Top-10 Cache Lines — R-W vs W-W stacked horizontal bar
  (b) Top-10 PC Hotspots — horizontal bar with source annotations
  (c) Cache line conflict distribution — cumulative CDF
  (d) Summary statistics panel
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import re
from pathlib import Path
from matplotlib.gridspec import GridSpec

# ── Research style (simple, clean, serif) ────────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "Georgia"],
    "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "legend.fontsize": 7.5, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.edgecolor": "#333", "axes.linewidth": 0.5,
    "axes.grid": False,
    "grid.color": "#ddd", "grid.linewidth": 0.3,
})

RESULTS = Path(__file__).parent.parent / "results"
OUT = Path(__file__).parent / "per_benchmark_figures"
OUT.mkdir(exist_ok=True)

RW_COLOR = "#0072B2"
WW_COLOR = "#D55E00"
MIXED_COLOR = "#999999"

BENCHMARKS = {
    "false_sharing":     "False Sharing (Synthetic)",
    "parallel_compress": "Parallel Compress",
    "word_count":        "Word Count (MapReduce)",
    "parallel_sort":     "Parallel Sort (Merge)",
    "duckdb":            "DuckDB (Analytical DB)",
}


def parse_report(path):
    """Parse a report_*.txt and return cache_lines[], pcs[], summary{}."""
    text = path.read_text()
    cache_lines = []
    pcs = []
    summary = {}

    # Parse cache lines section
    cl_pattern = re.compile(
        r"(0x[0-9a-fA-F]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.*)"
    )
    in_cl = False
    in_pc = False

    for line in text.splitlines():
        # Detect sections
        if "Potential False Sharing Candidates" in line:
            in_cl = True
            in_pc = False
            continue
        if "Top PCs by False Sharing" in line:
            in_cl = False
            in_pc = True
            continue
        if "--- Summary ---" in line:
            in_cl = False
            in_pc = False
            continue

        if line.startswith("---") or line.startswith("===") or line.startswith("Criteria"):
            continue
        if line.startswith("- Checking"):
            continue
        if "Cache Line" in line and "Total" in line:
            continue
        if "Rank" in line and "PC" in line:
            continue

        if in_cl:
            m = cl_pattern.match(line.strip())
            if m:
                addr = m.group(1)
                total = int(m.group(2))
                rw = int(m.group(3))
                ww = int(m.group(4))
                src = m.group(5).strip()
                # Shorten source
                src = re.sub(r"/qemu/benchmarks/", "", src)
                src = re.sub(r"\s*\(discriminator \d+\)", "", src)
                cache_lines.append({"addr": addr, "total": total, "rw": rw, "ww": ww, "src": src})

        if in_pc:
            # Format: Rank | PC | Conflicts | R-W | W-W | Source
            pc_pattern = re.compile(
                r"\d+\s*\|\s*(0x[0-9a-fA-F]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*(.*)"
            )
            m = pc_pattern.match(line.strip())
            if m:
                pc_addr = m.group(1)
                conflicts = int(m.group(2).replace(",", ""))
                rw = int(m.group(3).replace(",", ""))
                ww = int(m.group(4).replace(",", ""))
                src = m.group(5).strip()
                src = re.sub(r"/qemu/benchmarks/", "", src)
                src = re.sub(r"\s*\(discriminator \d+\)", "", src)
                if not src or src == "?":
                    src = f"[{pc_addr}]"
                pcs.append({"pc": pc_addr, "conflicts": conflicts, "rw": rw, "ww": ww, "src": src})

        # Summary lines
        if "Total conflicts:" in line:
            summary["total"] = int(line.split(":")[1].strip().replace(",", ""))
        if "Read-Write:" in line:
            summary["rw"] = int(line.split(":")[1].strip().replace(",", ""))
        if "Write-Write:" in line:
            summary["ww"] = int(line.split(":")[1].strip().replace(",", ""))
        if "Unique cache lines" in line:
            summary["cls"] = int(line.split(":")[1].strip().replace(",", ""))
        if "Unique PCs" in line:
            summary["pcs"] = int(line.split(":")[1].strip().replace(",", ""))

    return cache_lines, pcs, summary


def shorten_src(src, max_len=25):
    """Shorten source string for axis labels."""
    if len(src) <= max_len:
        return src
    # Take first source location
    parts = src.split(",")
    s = parts[0].strip()
    if len(s) > max_len:
        s = s[:max_len-2] + ".."
    return s


def thousands(x, pos=None):
    if abs(x) >= 1e6: return f"{x/1e6:.1f}M"
    if abs(x) >= 1e3: return f"{x/1e3:.0f}K"
    return f"{x:.0f}"


def generate_benchmark_plots(bench_key, bench_label):
    report_path = RESULTS / f"report_{bench_key}.txt"
    if not report_path.exists():
        print(f"  ✗ {bench_key}: report not found")
        return

    cache_lines, pcs, summary = parse_report(report_path)
    if not summary:
        print(f"  ✗ {bench_key}: could not parse summary")
        return

    total = summary.get("total", 1)
    n_cl = min(len(cache_lines), 10)
    n_pc = min(len(pcs), 10)

    # ═══════════════════════════════════════════════════════════════════════
    # 4-panel figure
    # ═══════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(12, 8.5), facecolor="white")
    gs = GridSpec(2, 2, figure=fig, hspace=0.38, wspace=0.32)

    # ─── Panel (a): Top Cache Lines — R-W vs W-W stacked bar ─────────────
    ax_a = fig.add_subplot(gs[0, 0])
    top_cl = cache_lines[:n_cl]

    if top_cl:
        y = np.arange(len(top_cl))
        rw_vals = [cl["rw"] for cl in top_cl]
        ww_vals = [cl["ww"] for cl in top_cl]
        cl_labels = []
        for cl in top_cl:
            short_addr = cl["addr"][-6:]  # last 6 hex digits
            src = shorten_src(cl["src"], 18) if cl["src"] else ""
            if src:
                cl_labels.append(f"..{short_addr}\n{src}")
            else:
                cl_labels.append(f"..{short_addr}")

        ax_a.barh(y, rw_vals, height=0.6, color=RW_COLOR, label="R-W",
                  edgecolor="white", linewidth=0.4, zorder=3)
        ax_a.barh(y, ww_vals, height=0.6, left=rw_vals, color=WW_COLOR,
                  label="W-W", edgecolor="white", linewidth=0.4, zorder=3)

        # Annotate totals
        for i, cl in enumerate(top_cl):
            pct = cl["total"] / total * 100
            ax_a.text(cl["total"] + total * 0.01, i, f"{cl['total']:,} ({pct:.1f}%)",
                      va="center", fontsize=6.5, color="#333")

        ax_a.set_yticks(y)
        ax_a.set_yticklabels(cl_labels, fontsize=6.5, fontfamily="monospace")
        ax_a.invert_yaxis()
        ax_a.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
        ax_a.legend(loc="lower right", fontsize=7, framealpha=0.9, edgecolor="#ccc")

    ax_a.set_xlabel("Conflicts")
    ax_a.set_title(f"(a) Top-{n_cl} Contended Cache Lines", fontweight="bold")
    ax_a.spines["top"].set_visible(False)
    ax_a.spines["right"].set_visible(False)

    # ─── Panel (b): Top PCs — horizontal bar with source ─────────────────
    ax_b = fig.add_subplot(gs[0, 1])
    top_pcs = pcs[:n_pc]

    if top_pcs:
        y = np.arange(len(top_pcs))
        pc_rw = [p["rw"] for p in top_pcs]
        pc_ww = [p["ww"] for p in top_pcs]
        pc_labels = []
        for p in top_pcs:
            src = p["src"]
            if src.startswith("["):
                pc_labels.append(src)
            else:
                pc_labels.append(shorten_src(src, 22))

        ax_b.barh(y, pc_rw, height=0.6, color=RW_COLOR, label="R-W",
                  edgecolor="white", linewidth=0.4, zorder=3)
        ax_b.barh(y, pc_ww, height=0.6, left=pc_rw, color=WW_COLOR,
                  label="W-W", edgecolor="white", linewidth=0.4, zorder=3)

        for i, p in enumerate(top_pcs):
            pct = p["conflicts"] / total * 100
            ax_b.text(p["conflicts"] + total * 0.01, i,
                      f"{p['conflicts']:,} ({pct:.1f}%)",
                      va="center", fontsize=6.5, color="#333")

        ax_b.set_yticks(y)
        ax_b.set_yticklabels(pc_labels, fontsize=6.5, fontfamily="monospace")
        ax_b.invert_yaxis()
        ax_b.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
        ax_b.legend(loc="lower right", fontsize=7, framealpha=0.9, edgecolor="#ccc")

    ax_b.set_xlabel("Conflicts")
    ax_b.set_title(f"(b) Top-{n_pc} PC Hotspots", fontweight="bold")
    ax_b.spines["top"].set_visible(False)
    ax_b.spines["right"].set_visible(False)

    # ─── Panel (c): Cumulative conflict distribution (CDF) ───────────────
    ax_c = fig.add_subplot(gs[1, 0])

    if cache_lines:
        sorted_cls = sorted(cache_lines, key=lambda x: x["total"], reverse=True)
        cumulative = np.cumsum([cl["total"] for cl in sorted_cls])
        cum_pct = cumulative / total * 100
        x_idx = np.arange(1, len(sorted_cls) + 1)

        ax_c.plot(x_idx, cum_pct, "o-", color=RW_COLOR, markersize=3,
                  linewidth=1.2, zorder=3)
        ax_c.fill_between(x_idx, cum_pct, alpha=0.1, color=RW_COLOR)

        # Mark 80% and 95% thresholds
        for thresh, ls in [(80, "--"), (95, ":")]:
            ax_c.axhline(y=thresh, color="#999", linestyle=ls, linewidth=0.6, alpha=0.6)
            # Find first index above threshold
            above = np.where(cum_pct >= thresh)[0]
            if len(above) > 0:
                idx = above[0]
                ax_c.plot(x_idx[idx], cum_pct[idx], "s", color=WW_COLOR,
                          markersize=5, zorder=4)
                ax_c.annotate(f"{thresh}% at {x_idx[idx]} lines",
                              xy=(x_idx[idx], cum_pct[idx]),
                              xytext=(x_idx[idx] + len(sorted_cls)*0.05, thresh - 5),
                              fontsize=7, color="#555",
                              arrowprops=dict(arrowstyle="-", color="#999", lw=0.5))

    ax_c.set_xlabel("Cache Lines (ranked by conflict count)")
    ax_c.set_ylabel("Cumulative % of Total Conflicts")
    ax_c.set_ylim(0, 105)
    ax_c.set_title("(c) Conflict Concentration (CDF)", fontweight="bold")
    ax_c.spines["top"].set_visible(False)
    ax_c.spines["right"].set_visible(False)
    ax_c.grid(True, alpha=0.3)

    # ─── Panel (d): Summary statistics ───────────────────────────────────
    ax_d = fig.add_subplot(gs[1, 1])
    ax_d.axis("off")

    rw_total = summary.get("rw", 0)
    ww_total = summary.get("ww", 0)
    rw_pct = rw_total / total * 100 if total else 0
    ww_pct = ww_total / total * 100 if total else 0
    n_cls = summary.get("cls", 0)
    n_pcs = summary.get("pcs", 0)
    cpl = total / n_cls if n_cls else 0

    # Top hotspot info
    top_pc_info = ""
    if pcs:
        top = pcs[0]
        top_pct = top["conflicts"] / total * 100
        top_pc_info = f"{top['src']}  ({top['conflicts']:,}, {top_pct:.1f}%)"

    top_cl_info = ""
    if cache_lines:
        top = cache_lines[0]
        top_pct = top["total"] / total * 100
        top_cl_info = f"{top['addr']}  ({top['total']:,}, {top_pct:.1f}%)"

    # Build table
    rows = [
        ("Total Conflicts",       f"{total:,}"),
        ("Read-Write (R-W)",      f"{rw_total:,}  ({rw_pct:.1f}%)"),
        ("Write-Write (W-W)",     f"{ww_total:,}  ({ww_pct:.1f}%)"),
        ("",                      ""),
        ("Unique Cache Lines",    f"{n_cls}"),
        ("Unique PCs",            f"{n_pcs}"),
        ("Conflicts / Cache Line", f"{cpl:.1f}"),
        ("",                      ""),
        ("#1 Cache Line",         top_cl_info),
        ("#1 PC Hotspot",         top_pc_info),
    ]

    y_start = 0.95
    for i, (label, value) in enumerate(rows):
        y_pos = y_start - i * 0.085
        if not label:
            continue
        ax_d.text(0.02, y_pos, label, transform=ax_d.transAxes,
                  fontsize=9, fontweight="bold", color="#333", va="top")
        ax_d.text(0.98, y_pos, value, transform=ax_d.transAxes,
                  fontsize=9, color="#555", va="top", ha="right", fontfamily="monospace")

    # R-W / W-W mini bar at the bottom
    bar_y = 0.08
    bar_h = 0.04
    import matplotlib.patches as mpatches
    rw_width = rw_pct / 100 * 0.96
    ww_width = ww_pct / 100 * 0.96
    ax_d.add_patch(mpatches.FancyBboxPatch(
        (0.02, bar_y), rw_width, bar_h, boxstyle="round,pad=0.002",
        facecolor=RW_COLOR, edgecolor="white", linewidth=0.5,
        transform=ax_d.transAxes))
    ax_d.add_patch(mpatches.FancyBboxPatch(
        (0.02 + rw_width, bar_y), ww_width, bar_h, boxstyle="round,pad=0.002",
        facecolor=WW_COLOR, edgecolor="white", linewidth=0.5,
        transform=ax_d.transAxes))
    ax_d.text(0.02 + rw_width/2, bar_y + bar_h/2, f"R-W {rw_pct:.0f}%",
              transform=ax_d.transAxes, ha="center", va="center",
              fontsize=7, color="white", fontweight="bold")
    if ww_pct > 5:
        ax_d.text(0.02 + rw_width + ww_width/2, bar_y + bar_h/2, f"W-W {ww_pct:.0f}%",
                  transform=ax_d.transAxes, ha="center", va="center",
                  fontsize=7, color="white", fontweight="bold")

    ax_d.set_title("(d) Summary Statistics", fontweight="bold")

    fig.suptitle(f"{bench_label}", fontsize=13, fontweight="bold", y=1.01)

    for ext in ["png", "pdf"]:
        fig.savefig(OUT / f"detail_{bench_key}.{ext}", facecolor="white")
    plt.close(fig)
    print(f"  + detail_{bench_key}")

    # ═══════════════════════════════════════════════════════════════════════
    # Standalone: PC contribution breakdown (pie/treemap style)
    # ═══════════════════════════════════════════════════════════════════════
    if pcs:
        fig2, ax2 = plt.subplots(figsize=(5.5, 3.5), facecolor="white")

        top_n = min(8, len(pcs))
        top_pcs_data = pcs[:top_n]
        top_sum = sum(p["conflicts"] for p in top_pcs_data)
        other = total - top_sum

        labels2 = [shorten_src(p["src"], 18) for p in top_pcs_data]
        vals2 = [p["conflicts"] for p in top_pcs_data]
        types2 = []
        for p in top_pcs_data:
            if p["ww"] > p["rw"]:
                types2.append(WW_COLOR)
            elif p["rw"] > 0 and p["ww"] > 0:
                types2.append(MIXED_COLOR)
            else:
                types2.append(RW_COLOR)

        if other > 0:
            labels2.append(f"Other ({summary.get('pcs', '?')- top_n} PCs)")
            vals2.append(other)
            types2.append("#CCCCCC")

        y2 = np.arange(len(labels2))
        ax2.barh(y2, vals2, height=0.6, color=types2,
                 edgecolor="white", linewidth=0.4, zorder=3)

        for i, v in enumerate(vals2):
            pct = v / total * 100
            ax2.text(v + total * 0.01, i, f"{pct:.1f}%",
                     va="center", fontsize=7, color="#555")

        ax2.set_yticks(y2)
        ax2.set_yticklabels(labels2, fontsize=7, fontfamily="monospace")
        ax2.invert_yaxis()
        ax2.set_xlabel("Conflicts")
        ax2.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
        ax2.set_title(f"{bench_label} -- PC Contribution Breakdown",
                      fontsize=10, fontweight="bold")
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)

        import matplotlib.patches as mpatches
        rw_p = mpatches.Patch(color=RW_COLOR, label="R-W dominant")
        ww_p = mpatches.Patch(color=WW_COLOR, label="W-W dominant")
        mx_p = mpatches.Patch(color=MIXED_COLOR, label="Mixed")
        ax2.legend(handles=[rw_p, ww_p, mx_p], loc="lower right", fontsize=6.5,
                   framealpha=0.9, edgecolor="#ccc")

        plt.tight_layout()
        for ext in ["png", "pdf"]:
            fig2.savefig(OUT / f"pcs_{bench_key}.{ext}", facecolor="white")
        plt.close(fig2)
        print(f"  + pcs_{bench_key}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
print("\n-- Generating per-benchmark detailed figures --")

for key, label in BENCHMARKS.items():
    generate_benchmark_plots(key, label)

# ═══════════════════════════════════════════════════════════════════════════════
# Cross-benchmark comparison: PC distribution (how many PCs cover 80%)
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6, 4), facecolor="white")

for key, label in BENCHMARKS.items():
    report_path = RESULTS / f"report_{key}.txt"
    if not report_path.exists():
        continue
    _, pcs_data, summ = parse_report(report_path)
    if not pcs_data or not summ:
        continue
    total = summ["total"]
    sorted_pcs = sorted(pcs_data, key=lambda x: x["conflicts"], reverse=True)
    cumulative = np.cumsum([p["conflicts"] for p in sorted_pcs])
    cum_pct = cumulative / total * 100
    x_idx = np.arange(1, len(sorted_pcs) + 1)

    short_label = label.split("(")[0].strip()
    ax.plot(x_idx, cum_pct, "o-", markersize=2.5, linewidth=1.2,
            label=f"{short_label} ({len(sorted_pcs)} PCs)", zorder=3)

ax.axhline(y=80, color="#999", linestyle="--", linewidth=0.6, alpha=0.6)
ax.axhline(y=95, color="#999", linestyle=":", linewidth=0.6, alpha=0.6)
ax.text(1, 81, "80%", fontsize=7, color="#777")
ax.text(1, 96, "95%", fontsize=7, color="#777")

ax.set_xlabel("PCs (ranked by conflict count)")
ax.set_ylabel("Cumulative % of Total Conflicts")
ax.set_ylim(0, 105)
ax.set_title("PC Conflict Concentration Across Benchmarks", fontweight="bold")
ax.legend(loc="lower right", fontsize=7, framealpha=0.9, edgecolor="#ccc")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(True, alpha=0.3)

plt.tight_layout()
for ext in ["png", "pdf"]:
    fig.savefig(OUT / f"cross_pc_concentration.{ext}", facecolor="white")
plt.close(fig)
print("  + cross_pc_concentration")

# ═══════════════════════════════════════════════════════════════════════════════
# Cross-benchmark: Cache line concentration overlay
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6, 4), facecolor="white")

for key, label in BENCHMARKS.items():
    report_path = RESULTS / f"report_{key}.txt"
    if not report_path.exists():
        continue
    cl_data, _, summ = parse_report(report_path)
    if not cl_data or not summ:
        continue
    total = summ["total"]
    sorted_cl = sorted(cl_data, key=lambda x: x["total"], reverse=True)
    cumulative = np.cumsum([cl["total"] for cl in sorted_cl])
    cum_pct = cumulative / total * 100
    x_idx = np.arange(1, len(sorted_cl) + 1)

    short_label = label.split("(")[0].strip()
    ax.plot(x_idx, cum_pct, "o-", markersize=2.5, linewidth=1.2,
            label=f"{short_label} ({len(sorted_cl)} CLs)", zorder=3)

ax.axhline(y=80, color="#999", linestyle="--", linewidth=0.6, alpha=0.6)
ax.axhline(y=95, color="#999", linestyle=":", linewidth=0.6, alpha=0.6)
ax.text(1, 81, "80%", fontsize=7, color="#777")
ax.text(1, 96, "95%", fontsize=7, color="#777")

ax.set_xlabel("Cache Lines (ranked by conflict count)")
ax.set_ylabel("Cumulative % of Total Conflicts")
ax.set_ylim(0, 105)
ax.set_title("Cache Line Conflict Concentration Across Benchmarks", fontweight="bold")
ax.legend(loc="lower right", fontsize=7, framealpha=0.9, edgecolor="#ccc")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(True, alpha=0.3)

plt.tight_layout()
for ext in ["png", "pdf"]:
    fig.savefig(OUT / f"cross_cl_concentration.{ext}", facecolor="white")
plt.close(fig)
print("  + cross_cl_concentration")

print(f"\nAll per-benchmark figures saved to {OUT}/")
