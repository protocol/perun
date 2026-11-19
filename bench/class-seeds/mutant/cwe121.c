/* Fictional Acme seed: CWE-121 mutant, renamed, unbounded copy of caller data into a stack array. */
#include <string.h>

void acme_tag(const char *user_text) {
    char tagbuf[16];
    strcpy(tagbuf, user_text);
}
