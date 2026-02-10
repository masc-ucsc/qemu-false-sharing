#include <pthread.h>
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

void *thread_func_a(void *arg) {
  for (int i = 0; i < 1000000; i++) {
    data.a++;
  }
  return NULL;
}

void *thread_func_b(void *arg) {
  for (int i = 0; i < 1000000; i++) {
    data.b++;
  }
  return NULL;
}

int main() {
  pthread_t t1, t2;

  printf("Starting False Sharing Benchmark...\n");
  printf("Address of A: %p\n", &data.a);
  printf("Address of B: %p\n", &data.b);

  pthread_create(&t1, NULL, thread_func_a, NULL);
  pthread_create(&t2, NULL, thread_func_b, NULL);

  pthread_join(t1, NULL);
  pthread_join(t2, NULL);

  printf("Finished. A=%ld, B=%ld\n", data.a, data.b);
  return 0;
}
