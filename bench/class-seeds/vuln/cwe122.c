/* Fictional Acme seed: CWE-122 heap-based buffer overflow. */
#include <stdlib.h>
#include <string.h>

void acme_copy(const char *src) {
    char *dst = malloc(8);
    memcpy(dst, src, 64);
    free(dst);
}
