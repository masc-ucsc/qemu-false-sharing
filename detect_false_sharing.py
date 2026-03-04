#!/usr/bin/env python3
"""Analyze QEMU false sharing summary produced by in-memory aggregation.

The instruction_log.txt now contains a compact summary with three sections:
  [cache_lines]  — per-cache-line conflict counts
  [pc_stats]     — per-PC conflict counts
  [summary]      — totals

This replaces the old row-per-instruction CSV approach, which generated
millions of rows and huge files.  The new format is typically < 100 lines.
"""
import sys
import csv
import argparse
import subprocess
import os
import io


def resolve_source_location(binary, address_hex):
    """Resolve a PC address to source file:line using addr2line or atos."""
    if not binary or not os.path.exists(binary):
        return "?"
    try:
        result = subprocess.run(
            ['addr2line', '-e', binary, address_hex],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip() and '??' not in result.stdout:
            return result.stdout.strip()
        result = subprocess.run(
            ['atos', '-o', binary, address_hex],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return "?"


def analyze_summary(filename, binary=None, check_read_write=True,
                    check_write_write=True, pc_hotspots=False):
    """Parse the new in-memory aggregated summary format."""

    cache_lines = []   # [(addr_int, total, rw, ww, [pc_hex, ...])]
    pc_stats = []      # [(pc_hex, loads, stores, rw, ww)]
    summary = {}

    print(f"Analyzing {filename}...")
    if binary:
        print(f"Using binary '{binary}' for source resolution.")

    try:
        with open(filename, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        return

    # Detect format: new summary format starts with '#' or '[cache_lines]'
    if not (content.startswith('#') or '[cache_lines]' in content):
        # Fall back to legacy CSV parsing
        analyze_legacy_csv(filename, binary, check_read_write,
                           check_write_write, pc_hotspots)
        return

    section = None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line == '[cache_lines]':
            section = 'cl'
            continue
        elif line == '[pc_stats]':
            section = 'pc'
            continue
        elif line == '[summary]':
            section = 'sum'
            continue

        if section == 'cl':
            if line.startswith('CacheLine,'):
                continue  # header
            parts = line.split(',', 4)
            if len(parts) < 4:
                continue
            addr = int(parts[0], 16)
            total = int(parts[1])
            rw = int(parts[2])
            ww = int(parts[3])
            pcs = parts[4].split(';') if len(parts) > 4 and parts[4] else []
            cache_lines.append((addr, total, rw, ww, pcs))

        elif section == 'pc':
            if line.startswith('PC,'):
                continue  # header
            parts = line.split(',')
            if len(parts) < 5:
                continue
            pc_hex = parts[0]
            loads = int(parts[1])
            stores = int(parts[2])
            rw_c = int(parts[3])
            ww_c = int(parts[4])
            pc_stats.append((pc_hex, loads, stores, rw_c, ww_c))

        elif section == 'sum':
            if '=' in line:
                k, v = line.split('=', 1)
                summary[k.strip()] = v.strip()

    # ── Output cache-line results ──
    print("\n=== Potential False Sharing Candidates (by Cache Line) ===")
    print("Criteria: High cross-core interaction (Ping-Pong)")
    if check_read_write:
        print("- Checking Read-Write Conflicts")
    if check_write_write:
        print("- Checking Write-Write Conflicts")

    print("-" * 80)
    print(f"{'Cache Line':<18} | {'Total':<6} | {'R-W':<6} | {'W-W':<6} | {'Source Locations'}")
    print("-" * 80)

    if not cache_lines:
        print("No cross-core interference detected matching criteria.")

    for addr, total, rw, ww, pcs in cache_lines[:20]:
        # Resolve source locations for contributing PCs
        sources = []
        for pc in pcs[:3]:
            pc = pc.strip()
            if pc and binary:
                src = resolve_source_location(binary, pc)
                if src != "?":
                    sources.append(src)
        src_str = ", ".join(sources)
        if len(pcs) > 3:
            src_str += "..."
        print(f"0x{addr:016x} | {total:<6} | {rw:<6} | {ww:<6} | {src_str}")

    # ── Output PC hot-spot results ──
    if pc_hotspots and pc_stats:
        print("\n=== Top PCs by False Sharing Conflicts (Hot-Spot Analysis) ===")
        print("-" * 90)
        print(f"{'Rank':<5} | {'PC':<20} | {'Conflicts':<12} | {'R-W':<8} | {'W-W':<8} | {'Source'}")
        print("-" * 90)

        for rank, (pc_hex, loads, stores, rw_c, ww_c) in enumerate(pc_stats[:20], 1):
            total_c = rw_c + ww_c
            src = resolve_source_location(binary, pc_hex) if binary else "?"
            print(f"{rank:<5} | {pc_hex:<20} | {total_c:>10,}   | {rw_c:>6,}   | {ww_c:>6,}   | {src}")

    # ── Summary ──
    total_conflicts = int(summary.get('total_conflicts', 0))
    total_rw = int(summary.get('rw_conflicts', 0))
    total_ww = int(summary.get('ww_conflicts', 0))
    n_cls = int(summary.get('unique_cache_lines', len(cache_lines)))
    n_pcs = int(summary.get('unique_pcs', len(pc_stats)))

    print(f"\n--- Summary ---")
    print(f"Total conflicts: {total_conflicts:,}")
    print(f"  Read-Write:  {total_rw:,}")
    print(f"  Write-Write: {total_ww:,}")
    print(f"Unique cache lines affected: {n_cls}")
    print(f"Unique PCs involved: {n_pcs}")


def analyze_legacy_csv(filename, binary=None, check_read_write=True,
                       check_write_write=True, pc_hotspots=False):
    """Parse the old per-instruction CSV format (backwards compatibility)."""
    last_writer = {}
    false_sharing_stats = {}
    pc_stats_dict = {}

    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    core = int(row['Core'])
                    addr_val = int(row['Address'], 16)
                    pc_hex = row['PC']
                    op = row['Op']
                    cache_line = addr_val & ~0x3F
                    conflict_type = None

                    if op == 'Store':
                        if cache_line in last_writer:
                            prev = last_writer[cache_line]
                            if prev['core'] != core:
                                if check_write_write:
                                    conflict_type = 'Write-Write'
                        last_writer[cache_line] = {'core': core, 'pc': pc_hex}
                    elif op in ('LoadHit', 'Load'):
                        if cache_line in last_writer:
                            prev = last_writer[cache_line]
                            if prev['core'] != core:
                                if check_read_write:
                                    conflict_type = 'Read-Write'

                    if conflict_type:
                        if cache_line not in false_sharing_stats:
                            false_sharing_stats[cache_line] = {
                                'count': 0, 'rw_count': 0, 'ww_count': 0,
                                'sources': set()
                            }
                        stat = false_sharing_stats[cache_line]
                        stat['count'] += 1
                        if conflict_type == 'Read-Write':
                            stat['rw_count'] += 1
                        else:
                            stat['ww_count'] += 1
                        if binary:
                            src_loc = resolve_source_location(binary, pc_hex)
                            if src_loc != "?":
                                stat['sources'].add(src_loc)

                        if pc_hex not in pc_stats_dict:
                            pc_stats_dict[pc_hex] = {
                                'count': 0, 'rw_count': 0, 'ww_count': 0
                            }
                        ps = pc_stats_dict[pc_hex]
                        ps['count'] += 1
                        if conflict_type == 'Read-Write':
                            ps['rw_count'] += 1
                        else:
                            ps['ww_count'] += 1

                except (ValueError, KeyError, TypeError):
                    continue
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        return

    print("\n=== Potential False Sharing Candidates (by Cache Line) ===")
    print("Criteria: High cross-core interaction (Ping-Pong)")
    if check_read_write:
        print("- Checking Read-Write Conflicts")
    if check_write_write:
        print("- Checking Write-Write Conflicts")
    print("-" * 80)
    print(f"{'Cache Line':<18} | {'Total':<6} | {'R-W':<6} | {'W-W':<6} | {'Source Locations'}")
    print("-" * 80)

    sorted_events = sorted(false_sharing_stats.items(),
                           key=lambda x: x[1]['count'], reverse=True)
    if not sorted_events:
        print("No cross-core interference detected matching criteria.")

    for line, data in sorted_events[:20]:
        sources_str = ", ".join(list(data['sources'])[:3])
        if len(data['sources']) > 3:
            sources_str += "..."
        print(f"0x{line:016x} | {data['count']:<6} | {data['rw_count']:<6} | {data['ww_count']:<6} | {sources_str}")

    if pc_hotspots and pc_stats_dict:
        print("\n=== Top PCs by False Sharing Conflicts (Hot-Spot Analysis) ===")
        print("-" * 90)
        print(f"{'Rank':<5} | {'PC':<20} | {'Conflicts':<12} | {'R-W':<8} | {'W-W':<8} | {'Source'}")
        print("-" * 90)
        sorted_pcs = sorted(pc_stats_dict.items(),
                            key=lambda x: x[1]['count'], reverse=True)
        for rank, (pc, data) in enumerate(sorted_pcs[:20], 1):
            src = resolve_source_location(binary, pc) if binary else "?"
            print(f"{rank:<5} | {pc:<20} | {data['count']:>10,}   | {data['rw_count']:>6,}   | {data['ww_count']:>6,}   | {src}")

    total_conflicts = sum(d['count'] for d in false_sharing_stats.values())
    total_rw = sum(d['rw_count'] for d in false_sharing_stats.values())
    total_ww = sum(d['ww_count'] for d in false_sharing_stats.values())
    print(f"\n--- Summary ---")
    print(f"Total conflicts: {total_conflicts:,}")
    print(f"  Read-Write:  {total_rw:,}")
    print(f"  Write-Write: {total_ww:,}")
    print(f"Unique cache lines affected: {len(false_sharing_stats)}")
    print(f"Unique PCs involved: {len(pc_stats_dict)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze QEMU false sharing summary (or legacy CSV log).")
    parser.add_argument("logfile", help="Path to instruction_log.txt")
    parser.add_argument("--binary",
                        help="Path to ELF binary for source line resolution",
                        default=None)
    parser.add_argument("--read-write", action="store_true",
                        help="Detect Read-Write conflicts")
    parser.add_argument("--write-write", action="store_true",
                        help="Detect Write-Write conflicts")
    parser.add_argument("--pc-hotspots", action="store_true",
                        help="Show top PCs by conflict frequency")
    args = parser.parse_args()

    rw = args.read_write
    ww = args.write_write
    if not rw and not ww:
        rw = True
        ww = True

    analyze_summary(args.logfile, args.binary, check_read_write=rw,
                    check_write_write=ww, pc_hotspots=args.pc_hotspots)
