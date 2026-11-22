/* Fictional Acme seed: CWE-476 mutant, renamed, null-checked after the dereference. */
#include <stdlib.h>

struct acme_node { int val; };

int acme_val(struct acme_node *node) {
    int v = node->val;
    if (node == NULL) {
        return 0;
    }
    return v;
}
