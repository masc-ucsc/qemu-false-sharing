/*
 * parallel_sort.c - Parallel merge sort
 *
 * Models the algorithm used in:
 *   - Java Arrays.parallelSort (JDK 8+, ForkJoin framework)
 *   - C++ std::sort with execution::par (libstdc++ TBB backend)
 *   - GNU sort --parallel
 *
 * Algorithm:
 *   1. Divide array into NUM_THREADS equal segments
 *   2. Each thread sorts its segment in-place (qsort)
 *   3. Parallel merge: thread 0 merges halves while thread 1 is idle
 *      (simplified — a full parallel merge tree is the real version)
 *
 * False sharing targets:
 *   a. The 'done' flags in merge_state sit in one cache line —
 *      threads write their flag as the other thread reads it.
 *   b. The boundary elements of adjacent sorted segments share a cache
 *      line; the merge step reads/writes them from different cores.
 */

#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── tunables ─────────────────────────────────────────────────── */
#define NUM_THREADS  2
#define ARRAY_SIZE   512          /* 512 64-bit integers             */

/* ── per-thread sort task ─────────────────────────────────────── */
typedef struct {
    int       tid;
    uint64_t *arr;
    size_t    lo;    /* inclusive                                   */
    size_t    hi;    /* exclusive                                   */
} SortTask;

/* merge state: all flags on one cache line → false sharing         */
static struct {
    volatile int done[NUM_THREADS];   /* 1 when sort phase complete  */
    volatile int merge_done;
    /* no padding: done[0] and done[1] share the same cache line    */
} merge_state;

static uint64_t *work_array;   /* shared input/output               */
static uint64_t *temp_array;   /* merge scratch buffer              */

/* ── comparison function for qsort ───────────────────────────── */
static int cmp_u64(const void *a, const void *b)
{
    uint64_t x = *(const uint64_t *)a;
    uint64_t y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

/* ── merge two sorted halves into temp, copy back ────────────── */
static void merge(uint64_t *arr, size_t lo, size_t mid, size_t hi,
                  uint64_t *tmp)
{
    size_t i = lo, j = mid, k = lo;
    while (i < mid && j < hi)
        tmp[k++] = (arr[i] <= arr[j]) ? arr[i++] : arr[j++];
    while (i < mid) tmp[k++] = arr[i++];
    while (j < hi)  tmp[k++] = arr[j++];
    memcpy(arr + lo, tmp + lo, (hi - lo) * sizeof *arr);
}

/* ── sort thread ──────────────────────────────────────────────── */
static void *sort_thread(void *arg)
{
    SortTask *t = arg;

    /* phase 1: sort own segment */
    qsort(work_array + t->lo, t->hi - t->lo, sizeof *work_array, cmp_u64);

    /* signal completion — write to done[tid]; the merge thread reads it.
       done[0] and done[1] sit in the same cache line → false sharing. */
    merge_state.done[t->tid] = 1;

    /* phase 2: thread 0 does the merge once both are done */
    if (t->tid == 0) {
        /* spin until thread 1 is done */
        while (!merge_state.done[1])
            ;   /* busy-wait: reads done[1] while thread 1 writes it */

        merge(work_array, 0, ARRAY_SIZE / 2, ARRAY_SIZE, temp_array);
        merge_state.merge_done = 1;
    }

    return NULL;
}

/* ── validate sorted array ────────────────────────────────────── */
static int is_sorted(uint64_t *arr, size_t n)
{
    for (size_t i = 1; i < n; i++)
        if (arr[i] < arr[i-1]) return 0;
    return 1;
}

/* ── main ─────────────────────────────────────────────────────── */
int main(int argc, char *argv[])
{
    int iterations = 100;
    if (argc > 1) iterations = atoi(argv[1]);
    if (iterations <= 0) iterations = 100;

    work_array = malloc(ARRAY_SIZE * sizeof *work_array);
    temp_array = malloc(ARRAY_SIZE * sizeof *temp_array);

    /* seed the array once with pseudo-random values */
    uint32_t rng = 0xCAFEBABE;
    for (size_t i = 0; i < ARRAY_SIZE; i++) {
        rng = rng * 1664525 + 1013904223;
        work_array[i] = ((uint64_t)rng << 17) ^ rng;
    }

    /* save original for reset between iterations */
    uint64_t *orig = malloc(ARRAY_SIZE * sizeof *orig);
    memcpy(orig, work_array, ARRAY_SIZE * sizeof *work_array);

    int ok = 1;
    for (int iter = 0; iter < iterations; iter++) {
        /* reset */
        memcpy(work_array, orig, ARRAY_SIZE * sizeof *work_array);
        memset(&merge_state, 0, sizeof merge_state);

        pthread_t threads[NUM_THREADS];
        SortTask  tasks[NUM_THREADS];
        size_t chunk = ARRAY_SIZE / NUM_THREADS;

        for (int i = 0; i < NUM_THREADS; i++) {
            tasks[i].tid = i;
            tasks[i].arr = work_array;
            tasks[i].lo  = i * chunk;
            tasks[i].hi  = (i == NUM_THREADS - 1) ? ARRAY_SIZE : (i + 1) * chunk;
            pthread_create(&threads[i], NULL, sort_thread, &tasks[i]);
        }
        for (int i = 0; i < NUM_THREADS; i++)
            pthread_join(threads[i], NULL);

        if (iter == iterations - 1)
            ok = is_sorted(work_array, ARRAY_SIZE);
    }

    printf("[parallel_sort] %d iteration(s) of %d elements, result %s\n",
           iterations, ARRAY_SIZE, ok ? "SORTED OK" : "SORT FAILED");

    free(work_array);
    free(temp_array);
    free(orig);
    return ok ? 0 : 1;
}
