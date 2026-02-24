#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

// 64-byte alignment to match cache line size
typedef struct {
  long counter;
  long padding[7]; // Ensures next counter is in next 64-byte chunk IF we want
                   // to avoid FS. But here we want FS, so let's put them close.
} Data;

// To force False Sharing, we put two counters in the SAME cache line.
// A cache line is typically 64 bytes.
// sizeof(long) = 8 bytes.
// If we have an array of longs, they are next to each other.

typedef struct {
  long a; // Thread 0 writes here
  long b; // Thread 1 writes here
          // These are 8 bytes apart, definitely in same 64-byte line
} FalseSharingData;

FalseSharingData data;

static long parse_iterations(int argc, char **argv) {
  const char *env_iters = getenv("ITERATIONS");
  const char *arg = (argc > 1) ? argv[1] : env_iters;
  if (!arg || !*arg) {
    return 1000000;
  }
  char *end = NULL;
  long val = strtol(arg, &end, 10);
  if (end == arg || val <= 0) {
    return 1000000;
  }
  return val;
}

void *thread_func_a(void *arg) {
  long iters = (long)(intptr_t)arg;
  for (long i = 0; i < iters; i++) {
    data.a++;
  }
  return NULL;
}

void *thread_func_b(void *arg) {
  long iters = (long)(intptr_t)arg;
  for (long i = 0; i < iters; i++) {
    data.b++;
  }
  return NULL;
}

int main(int argc, char **argv) {
  pthread_t t1, t2;
  long iters = parse_iterations(argc, argv);

  printf("Starting False Sharing Benchmark...\n");
  printf("Iterations: %ld\n", iters);
  printf("Address of A: %p\n", &data.a);
  printf("Address of B: %p\n", &data.b);

  pthread_create(&t1, NULL, thread_func_a, (void *)(intptr_t)iters);
  pthread_create(&t2, NULL, thread_func_b, (void *)(intptr_t)iters);

  pthread_join(t1, NULL);
  pthread_join(t2, NULL);

  printf("Finished. A=%ld, B=%ld\n", data.a, data.b);
  return 0;
}
