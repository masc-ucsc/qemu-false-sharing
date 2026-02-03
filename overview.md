# Overview

project: False sharing analysis via weak-consistency “store buffering” in QEMU (RISC-V)

author: Vijay Arvind Ramamoorthy (viramamo@ucsc.edu)

github: https://github.com/masc-ucsc/qemu-false-sharing

## Summary

False sharing happens when multiple threads touch different words on the same cache line, creating high coherence traffic and large slowdowns in real systems. It is hard to diagnose because it depends on dynamic interleavings, subtle synchronization, and microarchitectural details (e.g., when stores become visible to other cores).

This project builds a QEMU-based instrumentation framework for studying false sharing and memory-ordering behavior on RISC-V. QEMU is not a timing model, so the focus is not on cycle-accurate coherence (e.g., MESI), but on *consistency/visibility* effects: RISC-V is weakly consistent and stores may remain buffered and not become visible to other cores until the *local* core executes a fence (remote-core fences do not “flush” other cores).

## Outputs / Deliverables

- A patched QEMU (RISC-V) that can model per-core store buffering with a tunable capacity and visibility rules
- A false-sharing/interaction logger (cache-line granularity) and scripts to aggregate results into plots in `data/`
- A small benchmark suite: microbenchmarks + one “real” workload path (e.g., Postgres or a database-like kernel)
- Final report (`report.pdf`) with evaluation results and lessons learned

## Evaluation Plan

- **Primary metrics (QEMU-friendly):** cache-line interaction counts (invalidations/ping-pong proxies), buffered-store lifetime (time/ops until visibility), # of “would-have-shared” events under different buffering, fence frequency
- **Sensitivity study:** sweep “buffering strength” (buffer size / flush policy) and quantify how false-sharing indicators change
- **Bug-finding signal:** detect hangs/deadlocks or missed-progress scenarios that appear only when buffering is enabled (suggesting missing synchronization/fences)
- **Possible Race counter:** When a remote core access a still not performed (no fence), we can have a potential bug (it may be fine if there is a local fence relatively soon and the remote core can work with old stale data). Usually, it is fine if the "age" of race counters is not out of order.
- **Baselines:** buffering disabled (stores immediately visible), buffering enabled at multiple sizes, plus selected fence policies (strict vs relaxed flush on overflow)

## System Design / Architecture

### Project Options

**OPT1 (recommended): Consistency-focused store-buffer instrumentation (RISC-V).**
- Model weak consistency by delaying store visibility using a per-core bounded buffer (e.g., hash-map keyed by address/cache-line with a max size)
- Commit/flush buffered stores only on *local* fence instructions (and optionally on overflow, configurable)
- Applications:
  - Quantize “false sharing potential” under different buffering strengths (how much interaction is amplified/reduced when stores are not immediately visible)
  - Expose/triage correctness bugs (missing fences) by identifying deadlocks/hangs that appear when buffering is enabled

**OPT2 (backup): Coherence-style MESI tracking/mitigation in QEMU (not timing-accurate).**
- Keep the earlier MESI/coherence idea as a secondary direction, implemented as a software cache-line state tracker layered over QEMU memory ops
- Use it mainly for *detection* experiments and hypothesis testing (since QEMU does not provide a cycle-accurate coherence/timing model)

### Main Components (shared)

- **QEMU instrumentation hooks:** intercept loads/stores/fences, map addresses to cache lines, tag by vCPU/core
- **Event buffer + logging:** record relevant events (store buffered, store becomes visible, line accessed by multiple cores, fence) with throttling to keep overhead manageable
- **Analysis scripts:** aggregate logs into per-benchmark metrics and plots stored in `data/`
- **Workload runner:** scripts to run QEMU + benchmarks reproducibly (config, seeds, timeouts)

### Interfaces

- A QEMU runtime knob for buffering (e.g., store-buffer size / policy), plus an enable/disable switch for tracing
- Log format (CSV/JSONL) with: timestamp/opcount, core id, address/cache-line id, event type, benchmark id
- Minimal scripts to run: `./run_bench.sh --qemu <path> --bufsize <N> --workload <name>`

### Dependencies / Tech Stack

- QEMU (TCG) with RISC-V target enabled
- C for QEMU modifications; Python/bash for analysis and plotting
- Benchmark workloads (microbenchmarks + Postgres or a representative kernel)

## Timeline for main Components

- Week 1-2: build QEMU, locate load/store/fence paths for RISC-V, implement trace-only baseline (no buffering)
- Week 3-4: implement OPT1 store buffer + tunable size/policies; validate with litmus-style tests
- Week 5-7: run sensitivity study (buffer sweep) + collect data/plots; add deadlock/hang detection harness
- Week 8-10: refine analysis, write report, and (if time) prototype parts of OPT2 as a comparison point

## Current Status

- **Phase 1 Complete:**  Core Store Buffer mechanism implemented.
    - Added `StoreBuffer` struct and helper functions (`helper_sb_write`, `helper_sb_read`).
    - Implemented `GHashTable`-based statistics tracking for cache-line writes and forwarding hits.
    - Fixed build system issues related to `osdep.h` inclusions.
    - Verified `instruction_log.txt` output with implicit MESI state ("Modified (SB)").
- **Phase 2 (Next):** Instrumentation.
    - Next steps: Hooking `gen_store` and `gen_load` in `trans_rvi.c.inc` to use the new Store Buffer helpers.

## References

- RISC-V ISA + Memory Model / fence semantics (Ztso/rvwmo documentation)
- QEMU documentation (TCG, RISC-V target internals, memory helpers)
- False sharing background: Intel/AMD tuning guides; “false sharing” performance case studies and benchmarks
