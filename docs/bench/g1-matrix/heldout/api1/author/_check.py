import json, os, re, collections
m = json.load(open('cases.json'))
bad = re.compile(r'vuln|insecure|unsafe|safe|todo|fixme|exploit|flaw|idor|bola|owasp|api\s?\d+|bypass|attack', re.I)
errs = []
pos = [c for c in m if c['kind'] == 'pos']; neg = [c for c in m if c['kind'] == 'neg']
if (len(m), len(pos), len(neg)) != (30, 15, 15): errs.append(('counts', len(m), len(pos), len(neg)))
for c in m:
    d = os.path.join('cases', c['id'])
    files = [os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs]
    if not 1 <= len(files) <= 3: errs.append((c['id'], 'nfiles'))
    for f in files:
        t = open(f).read(); n = len(t.splitlines())
        if not 15 <= n <= 80: errs.append((f, 'lines', n))
        if bad.search(t): errs.append((f, 'banned', bad.search(t).group()))
        if '@@T' in t: errs.append((f, 'marker'))
    if c['kind'] == 'pos':
        p = os.path.join('cases', c['truth_file']); L = open(p).read().splitlines()
        tl = c['truth_line']
        if not (1 <= tl <= len(L)) or not re.search(r'get|find|first|fetch|SELECT|\[|filter', L[tl-1]): errs.append((c['id'], 'truth', tl))
fw = collections.Counter((c['framework'], c['kind']) for c in m)
print(dict(fw)); print('ERRORS' if errs else 'CLEAN', errs)
