/* Fictional Acme seed: CWE-121 fixed twin. */
#include <string.h>

void acme_label(void) {
    char b[8];
    strncpy(b, "far longer than eight bytes", sizeof b - 1);
    b[sizeof b - 1] = '\0';
}
