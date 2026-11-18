/* Fictional Acme seed: CWE-122 fixed twin. */
#include <stdlib.h>
#include <string.h>

void acme_copy(const char *src) {
    char *dst = malloc(64);
    memcpy(dst, src, 64);
    free(dst);
}
