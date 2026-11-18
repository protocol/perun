/* Fictional Acme seed: CWE-125 out-of-bounds read. */
int acme_last_score(void) {
    int scores[4] = {10, 20, 30, 40};
    return scores[4];
}
