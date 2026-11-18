/* Fictional Acme seed: CWE-416 fixed twin, use happens before free. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void acme_greet(const char *name) {
    char *msg = malloc(32);
    strncpy(msg, name, 31);
    msg[31] = '\0';
    printf("hello %s\n", msg);
    free(msg);
}
