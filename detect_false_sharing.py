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

def analyze_log(filename, binary=None, check_read_write=True, check_write_write=True):
    # Dictionary to track the last core that modified a cache line
    # Key: CacheLine Address (aligned to 64 bytes)
    # Value: { 'core': Core ID, 'pc': PC Address (Hex String) }
    last_writer = {}
    
    # Dictionary to track False Sharing events
    # Key: CacheLine Address
    # Value: { 'count': Total Count, 'rw_count': Read-Write Count, 'ww_count': Write-Write Count, 'sources': Set of Source Locations }
    false_sharing_stats = {}

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
                    
                    # Calculate Cache Line Address (64-byte aligned)
                    cache_line = addr_val & ~0x3F
                    
                    conflict_type = None

                    if op == 'Store':
                        # Check specific Write-Write conflict
                        if cache_line in last_writer:
                            prev = last_writer[cache_line]
                            if prev['core'] != core:
                                if check_write_write:
                                    conflict_type = 'Write-Write'
                        
                        # Always update last writer
                        last_writer[cache_line] = {'core': core, 'pc': pc_hex}

                    elif op == 'LoadHit':
                        # Check specific Read-Write conflict
                        if cache_line in last_writer:
                            prev = last_writer[cache_line]
                            if prev['core'] != core:
                                if check_read_write:
                                    conflict_type = 'Read-Write'

                    if conflict_type:
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
                        
                        # Resolve source location if binary provided
                        if binary:
                            src_loc = resolve_source_location(binary, pc_hex)
                            if src_loc != "?":
                                stat['sources'].add(src_loc)

                except (ValueError, KeyError):
                    continue

    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        return

    # Output Results
    print("\n=== Potential False Sharing Candidates ===")
    print(f"Criteria: High cross-core interaction (Ping-Pong)")
    if check_read_write: print("- Checking Read-Write Conflicts")
    if check_write_write: print("- Checking Write-Write Conflicts")
    
    print("-" * 80)
    print(f"{'Cache Line':<18} | {'Total':<6} | {'R-W':<6} | {'W-W':<6} | {'Source Locations'}")
    print("-" * 80)
    
    sorted_events = sorted(false_sharing_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    
    if not sorted_events:
        print("No cross-core interference detected matching criteria.")
    
    for line, data in sorted_events:
        sources_str = ", ".join(list(data['sources'])[:3]) # Limit to 3 sources
        if len(data['sources']) > 3:
            sources_str += "..."
            
        print(f"0x{line:016x} | {data['count']:<6} | {data['rw_count']:<6} | {data['ww_count']:<6} | {sources_str}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze QEMU instruction log for false sharing.")
    parser.add_argument("logfile", help="Path to instruction_log.txt")
    parser.add_argument("--binary", help="Path to ELF binary for source line resolution", default=None)
    parser.add_argument("--read-write", action="store_true", help="Detect Read-Write conflicts (default: True)")
    parser.add_argument("--write-write", action="store_true", help="Detect Write-Write conflicts (default: True)")
    # If neither flag is set, enable both (default behavior)
    args = parser.parse_args()
    
    rw = args.read_write
    ww = args.write_write
    if not rw and not ww:
        rw = True
        ww = True
        
    analyze_log(args.logfile, args.binary, check_read_write=rw, check_write_write=ww)
