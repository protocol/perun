/* Fictional Acme seed: CWE-416 mutant, renamed, a struct member read through the pointer right after free(). */
#include <stdlib.h>

struct acme_slot { int count; };

int acme_count(void) {
    struct acme_slot *slot = malloc(sizeof(struct acme_slot));
    if (!slot) return -1;
    slot->count = 0;
    free(slot);
    int n = slot->count;
    return n;
}
