/* Fictional Acme seed: CWE-476 NULL pointer dereference. */
#include <stdlib.h>

struct acme_rec { int len; };

int acme_len(void) {
    struct acme_rec *r = malloc(sizeof *r);
    if (r == NULL) {
        return r->len;
    }
    int n = r->len;
    free(r);
    return n;
}
