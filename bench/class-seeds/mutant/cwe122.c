/* Fictional Acme seed: CWE-122 mutant, renamed, unbounded strcpy into a small heap block. */
#include <stdlib.h>
#include <string.h>

char *acme_dup(const char *text) {
    char *out = malloc(4);
    strcpy(out, text);
    return out;
}
