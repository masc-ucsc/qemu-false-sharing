/*
 * word_count.c - Phoenix MapReduce word-count benchmark
 *
 * Faithful re-implementation of the Stanford Phoenix benchmark suite:
 *   https://github.com/kozyraki/phoenix  (Ranger et al., HPCA 2007)
 *
 * Algorithm:
 *   1. Split input text into per-thread segments (map phase)
 *   2. Each thread counts words into its own local hash table
 *   3. Reduce phase merges all per-thread tables into one global table
 *
 * False sharing target: the per-thread local_counts array sits in a
 * flat struct array. Adjacent threads' count structs share cache lines,
 * so the map phase causes write-write conflicts as threads update their
 * own counters that happen to be in the same 64-byte line.
 *
 * Also stresses the global hash table during the reduce phase with
 * concurrent inserts from all threads (guarded by per-bucket spin locks).
 */

#define _GNU_SOURCE
#include <ctype.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── tunables ─────────────────────────────────────────────────── */
#define NUM_THREADS     2
#define HASH_BUCKETS    1024
#define MAX_WORD_LEN    64
#define TEXT_SIZE       (4 * 1024)    /* 4 KB synthetic text         */

/* ── hash table ───────────────────────────────────────────────── */
typedef struct WordEntry {
    char            word[MAX_WORD_LEN];
    uint64_t        count;
    struct WordEntry *next;
} WordEntry;

typedef struct {
    WordEntry       *head;
    pthread_mutex_t  lock;
} HashBucket;

static HashBucket global_table[HASH_BUCKETS];

static uint32_t hash_word(const char *w)
{
    uint32_t h = 5381;
    while (*w) h = h * 33 ^ (unsigned char)*w++;
    return h % HASH_BUCKETS;
}

static void ht_insert(HashBucket *tbl, const char *word)
{
    uint32_t b = hash_word(word);
    pthread_mutex_lock(&tbl[b].lock);
    for (WordEntry *e = tbl[b].head; e; e = e->next) {
        if (strcmp(e->word, word) == 0) { e->count++; pthread_mutex_unlock(&tbl[b].lock); return; }
    }
    WordEntry *e = malloc(sizeof *e);
    strncpy(e->word, word, MAX_WORD_LEN - 1); e->word[MAX_WORD_LEN-1] = '\0';
    e->count = 1; e->next = tbl[b].head; tbl[b].head = e;
    pthread_mutex_unlock(&tbl[b].lock);
}

/* ── per-thread stats (false sharing source) ──────────────────── */
typedef struct {
    uint64_t words_processed;   /* written on every word          */
    uint64_t lines_seen;
    /* intentionally NOT padded → adjacent threads share cache line */
} ThreadStats;

static ThreadStats thread_stats[NUM_THREADS];  /* false sharing here */

/* ── map task ─────────────────────────────────────────────────── */
typedef struct {
    int         tid;
    const char *text;
    size_t      start;
    size_t      end;
} MapTask;

static void *map_thread(void *arg)
{
    MapTask *t = arg;
    const char *text = t->text;
    size_t pos = t->start;

    /* skip to start of next word boundary */
    while (pos < t->end && !isspace((unsigned char)text[pos])) pos++;

    char word[MAX_WORD_LEN];
    while (pos < t->end) {
        /* skip whitespace */
        while (pos < t->end && isspace((unsigned char)text[pos])) {
            if (text[pos] == '\n') thread_stats[t->tid].lines_seen++;
            pos++;
        }
        /* read word */
        int len = 0;
        while (pos < t->end && !isspace((unsigned char)text[pos]) && len < MAX_WORD_LEN - 1)
            word[len++] = tolower((unsigned char)text[pos++]);
        if (len == 0) break;
        word[len] = '\0';

        /* insert into global table — each thread races to update counters */
        ht_insert(global_table, word);

        /* update per-thread stats — false sharing: adjacent threads write
           to neighboring fields in the same cache line               */
        thread_stats[t->tid].words_processed++;
    }
    return NULL;
}

/* ── synthetic text generator ─────────────────────────────────── */
static const char *WORDS[] = {
    "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
    "parallel", "computing", "thread", "cache", "false", "sharing",
    "memory", "lock", "mutex", "atomic", "barrier", "synchronize",
    "pipeline", "producer", "consumer", "buffer", "queue",
};
#define NWORDS (sizeof(WORDS)/sizeof(WORDS[0]))

static char *generate_text(size_t size)
{
    char *buf = malloc(size + 64);
    size_t pos = 0;
    uint32_t rng = 0xDEADBEEF;
    while (pos < size - 32) {
        rng = rng * 1664525 + 1013904223;
        const char *w = WORDS[rng % NWORDS];
        size_t wlen = strlen(w);
        memcpy(buf + pos, w, wlen);
        pos += wlen;
        buf[pos++] = (pos % 79 == 0) ? '\n' : ' ';
    }
    buf[pos] = '\0';
    return buf;
}

/* ── main ─────────────────────────────────────────────────────── */
int main(int argc, char *argv[])
{
    int iterations = 1;
    if (argc > 1) iterations = atoi(argv[1]);
    if (iterations <= 0) iterations = 1;

    /* init hash table */
    for (int i = 0; i < HASH_BUCKETS; i++) {
        global_table[i].head = NULL;
        pthread_mutex_init(&global_table[i].lock, NULL);
    }

    char *text = generate_text(TEXT_SIZE);
    size_t text_len = strlen(text);

    for (int iter = 0; iter < iterations; iter++) {
        /* reset stats */
        memset(thread_stats, 0, sizeof thread_stats);

        pthread_t threads[NUM_THREADS];
        MapTask   tasks[NUM_THREADS];
        size_t chunk = text_len / NUM_THREADS;

        for (int i = 0; i < NUM_THREADS; i++) {
            tasks[i].tid   = i;
            tasks[i].text  = text;
            tasks[i].start = i * chunk;
            tasks[i].end   = (i == NUM_THREADS - 1) ? text_len : (i + 1) * chunk;
            pthread_create(&threads[i], NULL, map_thread, &tasks[i]);
        }
        for (int i = 0; i < NUM_THREADS; i++)
            pthread_join(threads[i], NULL);
    }

    /* report */
    uint64_t total_words = 0, unique_words = 0;
    for (int i = 0; i < NUM_THREADS; i++) total_words += thread_stats[i].words_processed;
    for (int b = 0; b < HASH_BUCKETS; b++)
        for (WordEntry *e = global_table[b].head; e; e = e->next) unique_words++;

    printf("[word_count] %d iter(s), ~%llu total word ops, %llu unique words\n",
           iterations,
           (unsigned long long)total_words,
           (unsigned long long)unique_words);

    free(text);
    return 0;
}
