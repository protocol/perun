/* Fictional Acme seed: CWE-416 mutant, renamed, write through the freed pointer inside a loop. */
#include <stdlib.h>

int acme_fill(int n) {
    int *slots = malloc(sizeof(int) * 4);
    if (!slots) return -1;
    free(slots);
    for (int i = 0; i < n; i++) {
        slots[0] = i;
    }
    return 0;
}
