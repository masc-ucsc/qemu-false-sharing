# QEMU False Sharing & Concurrency Bug Detection

A modified QEMU RISC-V emulator that detects **false sharing** and **concurrency bugs** at the instruction level — like a lightweight Valgrind DRD, but built into the CPU simulator.

## Quick Start

```bash
git clone <this-repo>
cd qemu
./run_user_test.sh
```

**Requirements:** Docker Desktop (will be prompted if missing).

That's it. The script builds everything inside Docker and runs the analysis automatically.

## What It Does

Every **load** and **store** instruction is intercepted and routed through a per-CPU **store buffer**. This lets us:

1. **Detect False Sharing** — Two threads touching different variables on the same cache line (64-byte aligned)
2. **Track PC Hot-Spots** — Which program counter (source line) causes the most conflicts
3. **Log Memory Access Patterns** — CSV trace of every load/store with core ID, address, and PC

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────┐
│  RISC-V      │     │  qemu-riscv64     │     │  Analysis    │
│  Binary      │────▶│  with store       │────▶│  Script      │
│  (benchmark) │     │  buffer + logging │     │  (Python)    │
└──────────────┘     └───────────────────┘     └──────────────┘
                          │                          │
                     CLI Flags:                  Output:
                     -false-sharing-read       Top PCs by conflict
                     -false-sharing-write      Source file:line
                     -buffer-size 64           R-W / W-W breakdown
```

## Usage

### Basic (uses defaults)
```bash
./run_user_test.sh
```

### Custom buffer size
```bash
BUFFER_SIZE=128 ./run_user_test.sh
```

### Run a different benchmark
```bash
BENCHMARK=true_sharing ./run_user_test.sh
```

### Increase Docker memory (if build fails with OOM)
```bash
DOCKER_MEM=8g ./run_user_test.sh
```

## Output

Results are saved to `results/`:

- **`results/report.txt`** — False sharing analysis with PC hot-spots
- **`results/instruction_log.txt`** — Raw CSV trace (Core, PC, Op, Address, Value, Hit, Size)

### Example Report
```
=== Potential False Sharing Candidates (by Cache Line) ===
Cache Line         | Total  | R-W    | W-W    | Source Locations
0x0000000000402040 | 1,234  | 800    | 434    | false_sharing.c:27

=== Top PCs by False Sharing Conflicts (Hot-Spot Analysis) ===
Rank | PC                 | Conflicts  | R-W     | W-W     | Source
1    | 0x00000000010234   | 1,102      | 700     | 402     | false_sharing.c:27
2    | 0x00000000010240   | 132        | 100     | 32      | false_sharing.c:28
```

## QEMU Flags (for direct use)

If running `qemu-riscv64` directly (inside Docker or on a Linux host):

```bash
./build/qemu-riscv64 \
    -false-sharing-read \
    -false-sharing-write \
    -buffer-size 64 \
    -deadlock-detector \
    your_program.rv64
```

| Flag | Description |
|------|-------------|
| `-false-sharing-read` | Detect read-write conflicts (different core reads a cache line another core wrote) |
| `-false-sharing-write` | Detect write-write conflicts (two cores writing same cache line) |
| `-buffer-size N` | Store buffer capacity (default: 64 entries) |
| `-deadlock-detector` | Enable deadlock detection via atomic instruction tracking |

## Benchmarks Included

| File | What It Tests |
|------|--------------|
| `benchmarks/false_sharing.c` | Two threads writing adjacent words on the same cache line (should trigger detection) |
| `benchmarks/true_sharing.c` | Producer-consumer with explicit shared counter (control — no false sharing) |

## How It Works (Architecture)

### Modified QEMU Files

| File | Role |
|------|------|
| `target/riscv/cpu.h` | `RISCVStoreBuffer` struct with per-CPU buffer, flags, stats hashmap |
| `target/riscv/op_helper.c` | `helper_sb_write/read/flush` — buffer logic + CSV logging |
| `target/riscv/insn_trans/trans_rvi.c.inc` | Hooks: Load→`sb_read`, Store→`sb_write`, Fence→`sb_flush` |
| `linux-user/main.c` | CLI argument parsing for `-false-sharing-*`, `-buffer-size`, `-deadlock-detector` |
| `detect_false_sharing.py` | Post-processing: cache-line aggregation, PC hot-spots, source resolution |

### Store Buffer Model

```
         Core 0                          Core 1
    ┌─────────────┐                ┌─────────────┐
    │ Store Buffer │                │ Store Buffer │
    │ ┌───┬───┬──┐│                │ ┌───┬───┬──┐│
    │ │302│307│  ││                │ │307│   │  ││
    │ │0xA│0xB│  ││                │ │0xF│   │  ││
    │ └───┴───┴──┘│                │ └───┴───┴──┘│
    └──────┬──────┘                └──────┬──────┘
           │         FENCE                │
           └──────────┬──────────────────┘
                      │ flush
                      ▼
              ┌───────────────┐
              │  Shared Memory │
              │  (Unified)     │
              │  addr 307 = ?  │  ← false sharing if
              └───────────────┘    same cache line
```

## Building Without Docker (Linux only)

```bash
mkdir build && cd build
../configure --target-list=riscv64-linux-user
ninja -j2
cd ..
riscv64-linux-gnu-gcc -g -O0 -static -pthread benchmarks/false_sharing.c -o benchmarks/false_sharing.rv64
./build/qemu-riscv64 -false-sharing-read -false-sharing-write -buffer-size 64 benchmarks/false_sharing.rv64
python3 detect_false_sharing.py instruction_log.txt --pc-hotspots
```
