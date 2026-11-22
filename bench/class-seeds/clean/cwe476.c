/* Fictional Acme seed: CWE-476 fixed twin. */
#include <stdlib.h>

struct acme_rec { int len; };

int acme_len(void) {
    struct acme_rec *r = malloc(sizeof *r);
    if (r == NULL) {
        return -1;
    }
    int n = r->len;
    free(r);
    return n;
}
