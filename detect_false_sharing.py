#!/usr/bin/env python3
import sys
import csv

def analyze_log(filename):
    # Dictionary to track the last core that modified a cache line
    # Key: CacheLine Address (aligned to 64 bytes)
    # Value: Core ID
    last_writer = {}
    
    # Dictionary to track False Sharing events
    # Key: CacheLine Address
    # Value: Count of "Ping Pong" events
    false_sharing_counts = {}

    print(f"Analyzing {filename}...")
    
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    core = int(row['Core'])
                    addr = int(row['Address'], 16)
                    op = row['Op']
                    
                    # Calculate Cache Line Address (64-byte aligned)
                    cache_line = addr & ~0x3F
                    
                    if op == 'Store':
                        # Check who wrote to this line last
                        if cache_line in last_writer:
                            prev_core = last_writer[cache_line]
                            
                            # If a DIFFERENT core wrote to it last, that's a "Ping Pong"
                            # Even if it's Write-after-Write, it invalidates the other core's cache
                            if prev_core != core:
                                false_sharing_counts[cache_line] = false_sharing_counts.get(cache_line, 0) + 1
                                
                        # Update last writer
                        last_writer[cache_line] = core

                    elif op == 'LoadHit':
                        # If we are reading something a DIFFERENT core wrote, that's a communication event
                        # (True sharing or False sharing)
                        if cache_line in last_writer:
                            prev_core = last_writer[cache_line]
                            if prev_core != core:
                                false_sharing_counts[cache_line] = false_sharing_counts.get(cache_line, 0) + 1
                                # We don't update last_writer for a read, typically, 
                                # but in MESI a read might change state to Shared.
                                # For simple ping-pong detection, tracking writers is most critical.

                except (ValueError, KeyError):
                    continue

    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        return

    # Output Results
    print("\n=== Potential False Sharing Candidates ===")
    print("Criteria: Cache lines with high cross-core interaction (Ping-Pong)")
    print(f"{'Cache Line':<20} | {'Interference Events':<20}")
    print("-" * 45)
    
    sorted_events = sorted(false_sharing_counts.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_events:
        print("No cross-core interference detected.")
    
    for line, count in sorted_events:
        print(f"0x{line:016x}   | {count:<20}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 detect_false_sharing.py <instruction_log.txt>")
    else:
        analyze_log(sys.argv[1])
