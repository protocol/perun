/* Fictional Acme seed: CWE-125 mutant, renamed, off-by-one loop bound. */
int acme_total(void) {
    int cells[5] = {1, 2, 3, 4, 5};
    int sum = 0;
    for (int k = 0; k <= 5; k++) {
        sum += cells[k];
    }
    return sum;
}
