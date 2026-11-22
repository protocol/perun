/* Fictional Acme seed: CWE-416 use after free, a read through the pointer right after free(). */
#include <stdlib.h>
#include <string.h>

int acme_first(const char *name) {
    char *msg = malloc(32);
    if (!msg) return -1;
    strncpy(msg, name, 31);
    msg[31] = '\0';
    free(msg);
    int first = *msg;
    return first;
}
