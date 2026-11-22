/* Fictional Acme seed: CWE-416 fixed twin, the read happens before free(). */
#include <stdlib.h>
#include <string.h>

int acme_first(const char *name) {
    char *msg = malloc(32);
    if (!msg) return -1;
    strncpy(msg, name, 31);
    msg[31] = '\0';
    int first = *msg;
    free(msg);
    return first;
}
