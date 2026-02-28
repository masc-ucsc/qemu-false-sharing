#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

/*
 * Deadlock Benchmark
 *
 * Two threads acquire two mutexes in opposite order, creating a classic
 * ABBA deadlock scenario.  Under QEMU with -deadlock-detector, the
 * instrumentation should detect the circular wait via amoswap tracking.
 *
 * Thread A: lock(m1) -> lock(m2) -> unlock(m2) -> unlock(m1)
 * Thread B: lock(m2) -> lock(m1) -> unlock(m1) -> unlock(m2)
 *
 * With a small sleep between the first and second lock, both threads
 * will likely hold one lock while requesting the other, triggering
 * deadlock detection.
 *
 * NOTE: We use trylock to avoid actually deadlocking the process,
 * which would hang QEMU forever.  The detector should still fire
 * because it observes the lock-order inversion.
 */

pthread_mutex_t mutex_a = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t mutex_b = PTHREAD_MUTEX_INITIALIZER;
volatile int shared_resource = 0;

static int parse_iterations(int argc, char **argv) {
    const char *env_iters = getenv("ITERATIONS");
    const char *arg = (argc > 1) ? argv[1] : env_iters;
    if (!arg || !*arg) {
        return 100;
    }
    char *end = NULL;
    long val = strtol(arg, &end, 10);
    if (end == arg || val <= 0) {
        return 100;
    }
    return (int)val;
}

void *thread_a(void *arg) {
    int iters = (int)(intptr_t)arg;
    int deadlock_attempts = 0;

    for (int i = 0; i < iters; i++) {
        /* Lock order: mutex_a then mutex_b */
        pthread_mutex_lock(&mutex_a);

        /* Try to lock mutex_b; if it would deadlock, back off */
        if (pthread_mutex_trylock(&mutex_b) == 0) {
            shared_resource++;
            pthread_mutex_unlock(&mutex_b);
        } else {
            deadlock_attempts++;
        }

        pthread_mutex_unlock(&mutex_a);
    }

    printf("Thread A: %d iterations, %d deadlock-avoided backoffs\n",
           iters, deadlock_attempts);
    return NULL;
}

void *thread_b(void *arg) {
    int iters = (int)(intptr_t)arg;
    int deadlock_attempts = 0;

    for (int i = 0; i < iters; i++) {
        /* Lock order: mutex_b then mutex_a (OPPOSITE order = deadlock risk) */
        pthread_mutex_lock(&mutex_b);

        /* Try to lock mutex_a; if it would deadlock, back off */
        if (pthread_mutex_trylock(&mutex_a) == 0) {
            shared_resource++;
            pthread_mutex_unlock(&mutex_a);
        } else {
            deadlock_attempts++;
        }

        pthread_mutex_unlock(&mutex_b);
    }

    printf("Thread B: %d iterations, %d deadlock-avoided backoffs\n",
           iters, deadlock_attempts);
    return NULL;
}

int main(int argc, char **argv) {
    pthread_t t1, t2;
    int iters = parse_iterations(argc, argv);

    printf("Starting Deadlock Detection Benchmark...\n");
    printf("Iterations: %d\n", iters);
    printf("Address of mutex_a: %p\n", (void *)&mutex_a);
    printf("Address of mutex_b: %p\n", (void *)&mutex_b);
    printf("Lock order: Thread A = (a,b), Thread B = (b,a) [ABBA pattern]\n\n");

    pthread_create(&t1, NULL, thread_a, (void *)(intptr_t)iters);
    pthread_create(&t2, NULL, thread_b, (void *)(intptr_t)iters);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);

    printf("\nFinished. shared_resource=%d (expected ~%d)\n",
           shared_resource, iters * 2);
    return 0;
}
