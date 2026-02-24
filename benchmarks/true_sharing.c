#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

// True Sharing: Thread A writes, Thread B reads the SAME variable.
// This is necessary communication.

volatile int shared_data = 0;
volatile int ready = 0;

static int parse_iterations(int argc, char **argv) {
  const char *env_iters = getenv("ITERATIONS");
  const char *arg = (argc > 1) ? argv[1] : env_iters;
  if (!arg || !*arg) {
    return 1000;
  }
  char *end = NULL;
  long val = strtol(arg, &end, 10);
  if (end == arg || val <= 0) {
    return 1000;
  }
  return (int)val;
}

void *producer(void *arg) {
  int iters = (int)(intptr_t)arg;
  for (int i = 0; i < iters; i++) {
    shared_data = i;
    // Memory barrier/fence would be here in real code
    __sync_synchronize();
    ready = 1;
    while (ready == 1) {
      // Wait for consumer
    }
  }
  return NULL;
}

void *consumer(void *arg) {
  int iters = (int)(intptr_t)arg;
  for (int i = 0; i < iters; i++) {
    while (ready == 0) {
      // Wait for producer
    }
    __sync_synchronize();
    if (shared_data != i) {
      printf("Error: expected %d, got %d\n", i, shared_data);
    }
    ready = 0;
  }
  return NULL;
}

int main(int argc, char **argv) {
  pthread_t t1, t2;
  int iters = parse_iterations(argc, argv);

  printf("Starting True Sharing Benchmark...\n");
  printf("Iterations: %d\n", iters);
  printf("Address of shared_data: %p\n", &shared_data);

  pthread_create(&t1, NULL, producer, (void *)(intptr_t)iters);
  pthread_create(&t2, NULL, consumer, (void *)(intptr_t)iters);

  pthread_join(t1, NULL);
  pthread_join(t2, NULL);

  printf("Finished.\n");
  return 0;
}
