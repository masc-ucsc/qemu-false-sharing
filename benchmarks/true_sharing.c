#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

// True Sharing: Thread A writes, Thread B reads the SAME variable.
// This is necessary communication.

volatile int shared_data = 0;
volatile int ready = 0;

void *producer(void *arg) {
  for (int i = 0; i < 1000; i++) {
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
  for (int i = 0; i < 1000; i++) {
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

int main() {
  pthread_t t1, t2;

  printf("Starting True Sharing Benchmark...\n");
  printf("Address of shared_data: %p\n", &shared_data);

  pthread_create(&t1, NULL, producer, NULL);
  pthread_create(&t2, NULL, consumer, NULL);

  pthread_join(t1, NULL);
  pthread_join(t2, NULL);

  printf("Finished.\n");
  return 0;
}
