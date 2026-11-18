/* Fictional Acme seed: CWE-416 use after free. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void acme_greet(const char *name) {
    char *msg = malloc(32);
    strncpy(msg, name, 31);
    msg[31] = '\0';
    free(msg);
    printf("hello %s\n", msg);
}
