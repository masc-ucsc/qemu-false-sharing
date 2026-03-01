/*
 * parallel_compress.c - Pigz-style parallel block processing pipeline
 *
 * Models the concurrency pattern from pigz (parallel gzip by Mark Adler):
 *   https://zlib.net/pigz/
 *
 * Architecture (same as pigz):
 *   - One producer thread reads/generates input blocks
 *   - N worker threads process blocks in parallel (here: CRC32 + checksum)
 *   - One writer thread serializes output in order
 *
 * False sharing target: the work queue head/tail indices and the
 * per-block 'done' flags sit adjacent in memory, causing cross-core
 * cache-line conflicts as workers update their slot and the writer
 * polls for completion.
 */

#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── tunables ─────────────────────────────────────────────────── */
#define BLOCK_SIZE   256          /* bytes per work block           */
#define QUEUE_DEPTH  8            /* pipeline queue slots           */
#define NUM_WORKERS  2            /* compressor threads             */

/* ── work block ───────────────────────────────────────────────── */
typedef struct {
    uint8_t  data[BLOCK_SIZE];
    uint32_t checksum;   /* result written by worker           */
    int      seq;        /* sequence number, -1 = sentinel     */
    volatile int done;   /* 0=pending, 1=processed             */
    /* pad to 64 bytes to isolate: comment out to trigger false sharing */
    /* char _pad[64 - sizeof(uint32_t) - sizeof(int) - sizeof(int)]; */
} WorkBlock;

/* ── shared pipeline queue ────────────────────────────────────── */
static WorkBlock queue[QUEUE_DEPTH];

/* head and tail are on the SAME cache line — classic false sharing
   between the producer (advances tail) and the writer (reads head).  */
static struct {
    volatile int head;   /* next slot for writer to consume    */
    volatile int tail;   /* next slot for producer to fill     */
    int total_blocks;
} pipeline;  /* all three fields in one 64-byte cache line          */

static pthread_mutex_t queue_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  work_ready = PTHREAD_COND_INITIALIZER;
static pthread_cond_t  slot_free  = PTHREAD_COND_INITIALIZER;
static volatile int    shutdown_workers = 0;

/* ── simple CRC32 (polynomial 0xEDB88320) ────────────────────── */
static uint32_t crc32_block(const uint8_t *buf, size_t len)
{
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= buf[i];
        for (int j = 0; j < 8; j++)
            crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
    }
    return ~crc;
}

/* ── worker thread ────────────────────────────────────────────── */
static void *worker_thread(void *arg)
{
    (void)arg;
    while (1) {
        /* scan queue for an undone, valid block */
        int found = 0;
        for (int i = 0; i < QUEUE_DEPTH; i++) {
            WorkBlock *blk = &queue[i];
            if (blk->seq < 0)
                continue;          /* empty slot               */
            if (blk->done)
                continue;          /* already processed        */

            /* claim it with a CAS-style double-check under lock */
            pthread_mutex_lock(&queue_lock);
            if (blk->seq >= 0 && !blk->done) {
                blk->done = 2;     /* mark "in progress"       */
                pthread_mutex_unlock(&queue_lock);

                blk->checksum = crc32_block(blk->data, BLOCK_SIZE);
                blk->done = 1;     /* false sharing: writer polls this */
                pthread_cond_signal(&work_ready);
                found = 1;
            } else {
                pthread_mutex_unlock(&queue_lock);
            }
        }

        if (!found) {
            pthread_mutex_lock(&queue_lock);
            if (shutdown_workers) {
                pthread_mutex_unlock(&queue_lock);
                break;
            }
            pthread_cond_wait(&work_ready, &queue_lock);
            if (shutdown_workers) {
                pthread_mutex_unlock(&queue_lock);
                break;
            }
            pthread_mutex_unlock(&queue_lock);
        }
    }
    return NULL;
}

/* ── writer thread ────────────────────────────────────────────── */
static void *writer_thread(void *arg)
{
    int total = *(int *)arg;
    uint64_t total_checksum = 0;
    int next_seq = 0;

    while (next_seq < total) {
        /* find the slot with seq == next_seq that is done */
        int found = 0;
        for (int i = 0; i < QUEUE_DEPTH; i++) {
            WorkBlock *blk = &queue[i];
            if (blk->seq == next_seq && blk->done == 1) {
                total_checksum += blk->checksum;
                /* free the slot */
                pthread_mutex_lock(&queue_lock);
                blk->seq = -1;
                blk->done = 0;
                pipeline.head = (pipeline.head + 1) % QUEUE_DEPTH;
                pthread_cond_signal(&slot_free);
                pthread_mutex_unlock(&queue_lock);
                next_seq++;
                found = 1;
                break;
            }
        }
        if (!found) {
            /* spin-wait — models pigz's writer busy-poll */
            pthread_mutex_lock(&queue_lock);
            pthread_cond_wait(&work_ready, &queue_lock);
            pthread_mutex_unlock(&queue_lock);
        }
    }

    printf("[writer] processed %d blocks, total checksum = 0x%016llx\n",
           total, (unsigned long long)total_checksum);
    return NULL;
}

/* ── main ─────────────────────────────────────────────────────── */
int main(int argc, char *argv[])
{
    int num_blocks = 200;
    if (argc > 1) num_blocks = atoi(argv[1]);
    if (num_blocks <= 0) num_blocks = 200;

    /* init queue */
    for (int i = 0; i < QUEUE_DEPTH; i++) { queue[i].seq = -1; queue[i].done = 0; }
    pipeline.head = 0;
    pipeline.tail = 0;
    pipeline.total_blocks = num_blocks;

    /* launch workers and writer */
    pthread_t workers[NUM_WORKERS], writer;
    for (int i = 0; i < NUM_WORKERS; i++)
        pthread_create(&workers[i], NULL, worker_thread, NULL);
    pthread_create(&writer, NULL, writer_thread, &num_blocks);

    /* producer: fill queue with blocks */
    for (int seq = 0; seq < num_blocks; seq++) {
        pthread_mutex_lock(&queue_lock);
        /* wait for a free slot */
        while (1) {
            int used = (pipeline.tail - pipeline.head + QUEUE_DEPTH) % QUEUE_DEPTH;
            if (used < QUEUE_DEPTH - 1) break;
            pthread_cond_wait(&slot_free, &queue_lock);
        }
        int slot = pipeline.tail % QUEUE_DEPTH;
        WorkBlock *blk = &queue[slot];
        /* fill with pseudo-random data */
        for (int j = 0; j < BLOCK_SIZE; j++)
            blk->data[j] = (uint8_t)((seq * 7 + j * 13) & 0xFF);
        blk->seq  = seq;
        blk->done = 0;
        pipeline.tail = (pipeline.tail + 1) % QUEUE_DEPTH;
        pthread_cond_broadcast(&work_ready);
        pthread_mutex_unlock(&queue_lock);
    }

    /* wait for writer to finish */
    pthread_join(writer, NULL);

    /* shut down workers */
    pthread_mutex_lock(&queue_lock);
    shutdown_workers = 1;
    pthread_cond_broadcast(&work_ready);
    pthread_mutex_unlock(&queue_lock);
    for (int i = 0; i < NUM_WORKERS; i++)
        pthread_join(workers[i], NULL);

    return 0;
}
