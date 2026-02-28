# Claude Code Prompt — QEMU False Sharing Detection Project

Copy everything below and paste it as your first message in Claude Code:

---

I'm working on a modified QEMU fork at `/Users/vijayarvind/Documents/Projects/qemu` that adds **false sharing detection** and **concurrency bug detection** to the RISC-V target. The project intercepts all Load/Store/Fence instructions and routes them through a per-CPU store buffer to detect cross-thread cache-line conflicts.

## Architecture (read these files to understand the project)

1. **`target/riscv/cpu.h`** (lines 216-242) — `RISCVStoreBuffer` struct, `SBEntry` struct, global externs
2. **`target/riscv/op_helper.c`** (lines 264-453) — Core logic: `helper_sb_write()`, `helper_sb_read()`, `do_sb_flush()`, CSV logging
3. **`target/riscv/helper.h`** (lines 124-128) — TCG helper declarations: `sb_write`, `sb_read`, `sb_flush`
4. **`target/riscv/insn_trans/trans_rvi.c.inc`** (lines 991-1001) — Fence → `helper_sb_flush`; also search for `helper_sb_write` and `helper_sb_read` calls
5. **`linux-user/main.c`** (lines 406-514) — CLI flags: `-false-sharing-read`, `-false-sharing-write`, `-buffer-size`, `-deadlock-detector`
6. **`target/riscv/cpu.c`** (lines 745-807) — Store buffer init/reset, global vars, log file setup
7. **`detect_false_sharing.py`** — Post-processing analysis script with `--pc-hotspots` mode
8. **`benchmarks/false_sharing.c`** — Test: two threads writing adjacent words on same cache line
9. **`benchmarks/true_sharing.c`** — Control: producer-consumer with explicit shared counter

## Data Flow

```
RISC-V binary → qemu-riscv64 (with flags) → instruction_log.txt (CSV) → detect_false_sharing.py → report
```

The CSV format is: `Core,PC,Op,Address,Value,Hit,Size`

## Current State

- ✅ Store buffer (write/read/flush) fully implemented
- ✅ Load/Store/Fence instruction hooks in trans_rvi.c.inc  
- ✅ CLI flags in linux-user/main.c
- ✅ CSV logging with per-core IDs
- ✅ Python analysis with PC hot-spot aggregation
- ✅ Dockerfile for user-mode build (macOS can't build linux-user natively)
- ⚠️ Docker image builds but the benchmark run hangs (may be too slow or threading issue in user mode)
- ❌ Deadlock detection not yet implemented
- ❌ End-to-end test not yet verified working

## What I Need Help With

The professor wants this to be **"git clone and run"**. Specifically:

1. **Get the end-to-end pipeline working**: `./run_user_test.sh` should build (via Docker), run the false_sharing benchmark under `qemu-riscv64`, and produce a report showing detected false sharing with source line numbers

2. **The benchmark might be hanging** — the `false_sharing.c` benchmark has 1,000,000 iterations per thread under QEMU emulation which may be too slow. Consider reducing iterations or adding a timeout

3. **Push the Docker image** to Docker Hub so the professor can skip the 10-min build (just `docker pull`)

## Key QEMU Coding Constraints

- `#include "qemu/osdep.h"` MUST be the first include in every .c file
- `GETPC()` can only be called from functions directly invoked by TCG — use `do_sb_flush(env, pc, GETPC())` pattern for nested calls
- User-mode core ID: use `env_cpu(env)->cpu_index`, NOT `env->mhartid`
- Format specifiers: use `PRIu64` for `uint64_t`, not `%lu`
- Cross-compile benchmarks with `-static -pthread` for user-mode

Please start by reading the key files listed above to understand what's implemented, then help me get the end-to-end test working.
