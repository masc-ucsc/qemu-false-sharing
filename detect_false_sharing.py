#!/usr/bin/env python3
import sys
import csv
import argparse
import subprocess
import os

def resolve_source_location(binary, address_hex):
    """
    Resolves a PC address to a source file and line number using available tools.
    """
    if not binary or not os.path.exists(binary):
        return "?"

    try:
        # Try `addr2line` (Linux/Cross-Platform)
        result = subprocess.run(
            ['addr2line', '-e', binary, address_hex],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip() and '??' not in result.stdout:
            return result.stdout.strip()

        # Try `atos` (macOS)
        # Note: atos requires load address for PIE binaries, assuming static/base for now
        result = subprocess.run(
            ['atos', '-o', binary, address_hex],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    except FileNotFoundError:
        pass
    
    return "?"

def analyze_log(filename, binary=None, check_read_write=True, check_write_write=True, pc_hotspots=False):
    # Dictionary to track the last core that modified a cache line
    last_writer = {}
    
    # Dictionary to track False Sharing events by cache line
    false_sharing_stats = {}

    # Dictionary to track False Sharing events by PC (hot-spot analysis)
    pc_stats = {}  # Key: PC hex string, Value: {'count', 'rw_count', 'ww_count'}

    print(f"Analyzing {filename}...")
    if binary:
        print(f"Using binary '{binary}' for source resolution.")

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

                    elif op == 'LoadHit':
                        if cache_line in last_writer:
                            prev = last_writer[cache_line]
                            if prev['core'] != core:
                                if check_read_write:
                                    conflict_type = 'Read-Write'

                    if conflict_type:
                        # Cache-line level stats
                        if cache_line not in false_sharing_stats:
                            false_sharing_stats[cache_line] = {
                                'count': 0, 'rw_count': 0, 'ww_count': 0, 'sources': set()
                            }
                        
                        stat = false_sharing_stats[cache_line]
                        stat['count'] += 1
                        if conflict_type == 'Read-Write':
                            stat['rw_count'] += 1
                        elif conflict_type == 'Write-Write':
                            stat['ww_count'] += 1
                        
                        if binary:
                            src_loc = resolve_source_location(binary, pc_hex)
                            if src_loc != "?":
                                stat['sources'].add(src_loc)

                        # PC-level stats (hot-spot analysis)
                        if pc_hex not in pc_stats:
                            pc_stats[pc_hex] = {'count': 0, 'rw_count': 0, 'ww_count': 0}
                        pc_stat = pc_stats[pc_hex]
                        pc_stat['count'] += 1
                        if conflict_type == 'Read-Write':
                            pc_stat['rw_count'] += 1
                        elif conflict_type == 'Write-Write':
                            pc_stat['ww_count'] += 1

                except (ValueError, KeyError):
                    continue

    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        return

    # Output Cache-Line Results
    print("\n=== Potential False Sharing Candidates (by Cache Line) ===")
    print(f"Criteria: High cross-core interaction (Ping-Pong)")
    if check_read_write: print("- Checking Read-Write Conflicts")
    if check_write_write: print("- Checking Write-Write Conflicts")
    
    print("-" * 80)
    print(f"{'Cache Line':<18} | {'Total':<6} | {'R-W':<6} | {'W-W':<6} | {'Source Locations'}")
    print("-" * 80)
    
    sorted_events = sorted(false_sharing_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    
    if not sorted_events:
        print("No cross-core interference detected matching criteria.")
    
    for line, data in sorted_events[:20]:  # Top 20
        sources_str = ", ".join(list(data['sources'])[:3])
        if len(data['sources']) > 3:
            sources_str += "..."
            
        print(f"0x{line:016x} | {data['count']:<6} | {data['rw_count']:<6} | {data['ww_count']:<6} | {sources_str}")

    # Output PC Hot-Spot Results
    if pc_hotspots and pc_stats:
        print("\n=== Top PCs by False Sharing Conflicts (Hot-Spot Analysis) ===")
        print("-" * 90)
        print(f"{'Rank':<5} | {'PC':<20} | {'Conflicts':<12} | {'R-W':<8} | {'W-W':<8} | {'Source'}")
        print("-" * 90)
        
        sorted_pcs = sorted(pc_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        
        for rank, (pc, data) in enumerate(sorted_pcs[:20], 1):
            src = resolve_source_location(binary, pc) if binary else "?"
            count_str = f"{data['count']:,}"
            rw_str = f"{data['rw_count']:,}"
            ww_str = f"{data['ww_count']:,}"
            print(f"{rank:<5} | {pc:<20} | {count_str:<12} | {rw_str:<8} | {ww_str:<8} | {src}")

    # Summary
    total_conflicts = sum(d['count'] for d in false_sharing_stats.values())
    total_rw = sum(d['rw_count'] for d in false_sharing_stats.values())
    total_ww = sum(d['ww_count'] for d in false_sharing_stats.values())
    print(f"\n--- Summary ---")
    print(f"Total conflicts: {total_conflicts:,}")
    print(f"  Read-Write:  {total_rw:,}")
    print(f"  Write-Write: {total_ww:,}")
    print(f"Unique cache lines affected: {len(false_sharing_stats)}")
    print(f"Unique PCs involved: {len(pc_stats)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze QEMU instruction log for false sharing.")
    parser.add_argument("logfile", help="Path to instruction_log.txt")
    parser.add_argument("--binary", help="Path to ELF binary for source line resolution", default=None)
    parser.add_argument("--read-write", action="store_true", help="Detect Read-Write conflicts")
    parser.add_argument("--write-write", action="store_true", help="Detect Write-Write conflicts")
    parser.add_argument("--pc-hotspots", action="store_true", help="Show top PCs by conflict frequency")
    args = parser.parse_args()
    
    rw = args.read_write
    ww = args.write_write
    if not rw and not ww:
        rw = True
        ww = True
        
    analyze_log(args.logfile, args.binary, check_read_write=rw, check_write_write=ww, pc_hotspots=args.pc_hotspots)

