# QEMU Concurrency Bug Detection Framework

A modified QEMU RISC-V emulator that detects **false sharing** and **deadlocks** at the instruction level -- like a lightweight Valgrind DRD, but built into the CPU simulator.

## One-Command Install

```bash
curl -LsSf https://raw.githubusercontent.com/vijayarvind/qemu/main/scripts/install.sh | sh
```

This single command clones the repo, builds QEMU inside Docker, cross-compiles benchmarks, and runs a smoke test. **Requirements:** Docker Desktop + git.

### Or manual setup:

```bash
git clone https://github.com/vijayarvind/qemu.git
cd qemu
./run_user_test.sh
```

That's it. The script builds everything inside Docker and runs the analysis automatically.

## What It Detects

### 1. False Sharing
Two threads touching **different variables** on the **same 64-byte cache line**. The tool logs every Load/Store and flags cross-core conflicts:
- **Read-Write conflicts** (core A reads a line core B wrote)
- **Write-Write conflicts** (two cores writing the same cache line)

### 2. Deadlocks (ABBA Lock-Order Inversion)
Two threads acquiring locks in **opposite order**. The tool intercepts `amoswap` (used by `pthread_mutex_lock`) and builds a wait-for graph. When a cycle is found, it prints which cores hold which locks and the source lines involved.

## Data Flow

```
RISC-V binary --> qemu-riscv64 (with flags) --> instruction_log.txt (CSV)
                       |                              |
                       |  stderr: DEADLOCK warnings   |
                       v                              v
                  results/stderr.txt         detect_false_sharing.py
                                                      |
                                                      v
                                              results/report.txt
```

CSV format: `Core,PC,Op,Address,Value,Hit,Size`

## Usage

### False Sharing Detection (default)
```bash
./run_user_test.sh
```

### Deadlock Detection
```bash
BENCHMARK=deadlock DEADLOCK=1 ./run_user_test.sh
```

### All Configuration Options
```bash
ITERATIONS=1000 ./run_user_test.sh        # more iterations (default: 500)
BUFFER_SIZE=128 ./run_user_test.sh         # larger store buffer (default: 64)
BENCHMARK=true_sharing ./run_user_test.sh  # control test (no false sharing expected)
TIMEOUT=300 ./run_user_test.sh             # longer timeout (default: 120s)
DOCKER_MEM=8g ./run_user_test.sh           # more RAM for Docker build
```

Combine them:
```bash
BENCHMARK=deadlock DEADLOCK=1 ITERATIONS=200 TIMEOUT=60 ./run_user_test.sh
```

## QEMU Flags (for direct use)

If running `qemu-riscv64` directly (inside Docker or on a Linux host):

```bash
./build/qemu-riscv64 \
    -false-sharing-read \
    -false-sharing-write \
    -buffer-size 64 \
    -deadlock-detector \
    your_program.rv64 500
```

| Flag | Description |
|------|-------------|
| `-false-sharing-read` | Detect read-write conflicts (different core reads a cache line another core wrote) |
| `-false-sharing-write` | Detect write-write conflicts (two cores writing same cache line) |
| `-buffer-size N` | Store buffer capacity (default: 64 entries) |
| `-deadlock-detector` | Enable deadlock detection via atomic instruction tracking |

## Output

Results are saved to `results/`:

| File | Contents |
|------|----------|
| `results/report.txt` | False sharing analysis with PC hot-spots + deadlock warnings |
| `results/instruction_log.txt` | Raw CSV trace (Core, PC, Op, Address, Value, Hit, Size) |
| `results/stderr.txt` | Runtime warnings including DEADLOCK detections with source lines |

### Example: False Sharing Report
```
=== Potential False Sharing Candidates (by Cache Line) ===
Cache Line         | Total  | R-W    | W-W    | Source Locations
0x0000000000402040 | 1,234  | 800    | 434    | false_sharing.c:43

=== Top PCs by False Sharing Conflicts (Hot-Spot Analysis) ===
Rank | PC                 | Conflicts  | R-W     | W-W     | Source
1    | 0x00000000010234   | 1,102      | 700     | 402     | false_sharing.c:43
```

### Example: Deadlock Detection Output
```
DEADLOCK: core 0 waits on lock 0x4b2060 at pc 0x10456 (deadlock.c:52),
  held by core 1 (acquired at pc 0x104a0 (deadlock.c:70)).
  Core 1 waits on lock 0x4b2030 at pc 0x104a4 (deadlock.c:72),
  held by core 0 (acquired at pc 0x10452 (deadlock.c:50)).
```

## Benchmarks & Evaluation Results

We evaluated the framework across **5 multi-threaded workloads** of increasing complexity. All benchmarks were cross-compiled for RISC-V and executed inside our instrumented QEMU emulator.

### Benchmark Suite

| Benchmark | Description | Source |
|-----------|-------------|--------|
| **False Sharing** | Two threads writing adjacent words on the same cache line (canonical false sharing) | `benchmarks/false_sharing.c` |
| **Parallel Compress** | Multi-threaded RLE compression of shared data buffers | `benchmarks/parallel_compress.c` |
| **Word Count** | Parallel MapReduce-style word frequency counter with shared hash table | `benchmarks/word_count.c` |
| **Parallel Sort** | Concurrent merge sort over a shared array | `benchmarks/parallel_sort.c` |
| **DuckDB** | Full DuckDB analytical database engine running TPC-H style queries | `benchmarks/duckdb/` |
| **True Sharing** | Producer-consumer with explicit shared counter (control — no false sharing expected) | `benchmarks/true_sharing.c` |
| **Deadlock** | Two threads acquiring two mutexes in opposite order (ABBA pattern) | `benchmarks/deadlock.c` |

### Results Summary

| Benchmark | Total Conflicts | R-W Conflicts | W-W Conflicts | Cache Lines | PCs Involved |
|-----------|----------------:|--------------:|--------------:|------------:|-------------:|
| False Sharing | 3,829 | 1,789 | 2,040 | 26 | 33 |
| Parallel Compress | 17,176 | 16,919 | 257 | 167 | 73 |
| Word Count | 227,808 | 216,763 | 11,045 | 247 | 112 |
| Parallel Sort | 208,458 | 180,041 | 28,417 | 208 | 134 |
| DuckDB | 203,579 | 203,265 | 314 | 378 | 922 |

**Key observations:**
- The **False Sharing** benchmark produces a concentrated hotspot on a single cache line (`0x7f440`) with ~50/50 R-W and W-W split, exactly as expected for co-located counter increments.
- **Word Count** and **Parallel Sort** show the highest conflict density, driven by shared hash-table and array boundary regions.
- **DuckDB** generates 203K+ conflicts spread across 378 cache lines and 922 unique PCs — demonstrating the tool handles real-world database engines at scale.
- All benchmarks are **R-W dominant** except False Sharing, which confirms that most real programs suffer from read-after-write ping-ponging rather than write-write races.

### Evaluation Figures

Combined benchmark visualizations are in [`paper/figures/`](paper/figures/):

| Figure | Description |
|--------|-------------|
| `combined_total_conflicts.png` | Total conflict counts across all benchmarks |
| `combined_rw_ww_stacked.png` | R-W vs W-W breakdown (stacked bar chart) |
| `combined_heatmap.png` | Conflict density heatmap by cache line |
| `combined_radar.png` | Multi-dimensional radar comparison |
| `combined_scatter_bubble.png` | Cache line vs PC scatter (bubble = severity) |
| `combined_dashboard_dark.png` | All-in-one dark-themed dashboard |
| `individual_*.png` | Per-benchmark detailed analysis panels |

To regenerate the plots:
```bash
pip install matplotlib numpy
python3 paper/generate_benchmark_plots.py
```

## How It Works (Architecture)

### Modified QEMU Files

| File | Role |
|------|------|
| `target/riscv/cpu.h` | `RISCVStoreBuffer` struct with per-CPU buffer, flags, stats hashmap |
| `target/riscv/op_helper.c` | `helper_sb_write/read/flush/amo_lock` -- buffer logic, CSV logging, deadlock detection |
| `target/riscv/translate.c` | `gen_amo`/`gen_amoswap` -- hooks atomic ops for deadlock tracking |
| `target/riscv/insn_trans/trans_rvi.c.inc` | Hooks: Load->`sb_read`, Store->`sb_write`, Fence->`sb_flush` |
| `linux-user/main.c` | CLI argument parsing for all `-false-sharing-*`, `-buffer-size`, `-deadlock-detector` flags |
| `detect_false_sharing.py` | Post-processing: cache-line aggregation, PC hot-spots, source-line resolution |

### Store Buffer Model

```
         Core 0                          Core 1
    +---------------+                +---------------+
    | Store Buffer  |                | Store Buffer  |
    | [addr|data]   |                | [addr|data]   |
    | [0xA0|  42 ]  |                | [0xA8| 99  ]  |
    | [0xB0|  17 ]  |                |               |
    +-------+-------+                +-------+-------+
            |         FENCE                  |
            +----------+--------------------+
                       | flush to shared memory
                       v
               +---------------+
               | Shared Memory |
               | 0xA0 = 42     | <-- same cache line (0xA0..0xBF)
               | 0xA8 = 99     | <-- false sharing!
               +---------------+
```

### Deadlock Detection Model

```
Thread A                    Thread B
   |                           |
   | lock(mutex_a)             | lock(mutex_b)
   | [amoswap -> amo_lock]     | [amoswap -> amo_lock]
   |                           |
   | lock(mutex_b) --> BLOCKED | lock(mutex_a) --> BLOCKED
   |                           |
   +------ CYCLE DETECTED -----+
   |                           |
   stderr: DEADLOCK: core 0 waits on lock held by core 1,
           core 1 waits on lock held by core 0
```

## Building Without Docker (Linux only)

```bash
# Build QEMU (user-mode only)
mkdir build && cd build
../configure --target-list=riscv64-linux-user --disable-system
ninja -j$(nproc)
cd ..

# Cross-compile benchmarks
riscv64-linux-gnu-gcc -g -O0 -static -pthread benchmarks/false_sharing.c -o benchmarks/false_sharing.rv64
riscv64-linux-gnu-gcc -g -O0 -static -pthread benchmarks/deadlock.c -o benchmarks/deadlock.rv64

# Run false sharing detection
./build/qemu-riscv64 -false-sharing-read -false-sharing-write -buffer-size 64 \
    benchmarks/false_sharing.rv64 500
python3 detect_false_sharing.py instruction_log.txt --binary benchmarks/false_sharing.rv64 --pc-hotspots

# Run deadlock detection
./build/qemu-riscv64 -deadlock-detector -buffer-size 64 \
    benchmarks/deadlock.rv64 100
# Deadlock warnings appear on stderr
```
