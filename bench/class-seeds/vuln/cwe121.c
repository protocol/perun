/* Fictional Acme seed: CWE-121 stack-based buffer overflow. */
#include <string.h>

void acme_label(void) {
    char b[8];
    strcpy(b, "far longer than eight bytes");
}
