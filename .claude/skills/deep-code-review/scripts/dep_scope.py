#!/usr/bin/env python3
"""Dependency scope of a pkg@version in an npm-ecosystem lockfile: reachable only via devDependencies, or not.

Library (stdlib only; load by path, run with `python3 -I`). `scope_sets(lockfile)` returns `(prod, dev)`, two sets of
"name@version", or None when the file is not a supported format or cannot be parsed (callers then add no tag).
Supported: package-lock.json with a "packages" map, i.e. v2/v3; v1 has none and is unknown ("dev": true marks dev; "devOptional" and untagged entries count as prod),
yarn.lock v1 and pnpm-lock.yaml v9 (walk the graph from package.json dependencies+optionalDependencies incl.
workspaces, resp. pnpm importers, versus devDependencies). A package in both sets is prod: callers tag dev only when
it is in `dev` and not in `prod`. Version match only: prod means shipped in the production tree, not exploitable.
CLI: dep_scope.py LOCKFILE... prints "dev<TAB>pkg@version" per dev-only package (self-check aid).
"""
import collections, glob, json, os, re, sys

def nm(spec):  # name part of "name@range" (scoped-safe)
    i = spec.index('@', 1) if spec.startswith('@') else spec.index('@')
    return spec[:i]

def tgt(s):  # real package name of a "name@range" spec; "alias@npm:real[@range]" -> real (loop, never recursion)
    while '@' in s[1:]:
        n = nm(s); r = s[len(n) + 1:]
        if not r.startswith('npm:'): return n
        s = r[4:]
    return s

def manifest_roots(d):
    pj = os.path.join(d, 'package.json'); prod, dev, ws = {}, {}, []
    if not os.path.exists(pj): return prod, dev
    m = json.load(open(pj)); wsg = m.get('workspaces') or []
    if isinstance(wsg, dict): wsg = wsg.get('packages') or []
    rd = os.path.realpath(d) + os.sep
    for g in wsg:  # recursive "**"; a match outside the lockfile dir is never read and fails closed (untagged)
        for p in glob.glob(os.path.join(d, g, 'package.json'), recursive=True):
            if not os.path.realpath(p).startswith(rd): raise ValueError('workspace outside lockfile dir')
            ws.append(p)
    for f in [pj] + ws:
        mm = json.load(open(f))
        for k in ('dependencies', 'optionalDependencies'): prod.update(mm.get(k) or {})
        dev.update(mm.get('devDependencies') or {})
    return prod, dev

def yarn_v1(path):
    ent, cur, sec = {}, None, None
    for line in open(path):
        if not line.strip() or line.startswith('#'): continue
        if not line.startswith(' '):
            specs = [s.strip().strip('"') for s in line.strip().rstrip(':').split(',')]
            cur = {'name': tgt(specs[0]), 'version': None, 'deps': {}, 'proto': any(':' in s[len(nm(s)) + 1:] and not s[len(nm(s)) + 1:].startswith('npm:') for s in specs if '@' in s[1:])}; sec = None
            for s in specs: ent[s] = cur
        elif line.startswith('    ') and sec in ('dependencies', 'optionalDependencies'):
            k, v = line.strip().split(' ', 1); cur['deps'][k.strip('"')] = v.strip('"')
        else:
            s = line.strip()
            if s.endswith(':'): sec = s[:-1]
            else:
                sec = None
                if s.startswith('version '): cur['version'] = s.split(' ', 1)[1].strip('"')
    byname = collections.defaultdict(list)
    for e in ent.values(): byname[e['name']].append(e)
    def walk(roots, strict=False):  # strict (prod): a non-registry entry has no real name in yarn v1 -> unknown, fail closed
        seen, st = set(), [f'{k}@{v}' for k, v in roots.items()]
        while st:
            s = st.pop(); e = ent.get(s)
            if not e:  # unresolved edge (e.g. resolutions): every locked copy of that name counts as reached (prod stays a superset)
                for x in byname.get(tgt(s), []):
                    if x['proto'] and strict: raise ValueError('prod URL/git alias')
                    if id(x) not in seen: seen.add(id(x)); st += [f'{k}@{v}' for k, v in x['deps'].items()]
                continue
            if e['proto'] and strict: raise ValueError('prod URL/git alias')
            if id(e) in seen: continue
            seen.add(id(e)); st += [f'{k}@{v}' for k, v in e['deps'].items()]
        return {f"{e['name']}@{e['version']}" for e in ent.values() if id(e) in seen}
    prod, dev = manifest_roots(os.path.dirname(path))
    return walk(prod, True), walk(dev)

def pnpm_v9(path):
    imp, snap, top, key, sub, dep = {'prod': {}, 'dev': {}}, collections.defaultdict(dict), None, None, None, None
    for line in open(path):
        if not line.strip(): continue
        ind = len(line) - len(line.lstrip(' ')); s = line.strip()
        if ind == 0: top = s.rstrip(':'); continue
        if top == 'importers':
            if ind == 2: key = s.rstrip(':')
            elif ind == 4: sub = s.rstrip(':')
            elif ind == 6: dep = s.rstrip(':').strip("'")
            elif ind == 8 and s.startswith('version:'):
                imp['dev' if sub == 'devDependencies' else 'prod'][f"{dep}@{s.split(':',1)[1].strip().strip(chr(39))}"] = 1
        elif top == 'snapshots':
            if ind == 2: key = s.removesuffix(' {}').rstrip(':').strip("'"); snap[key]  # leaf entries read "pkg@1.0.0: {}"
            elif ind == 4: sub = s.rstrip(':')
            elif ind == 6 and sub in ('dependencies', 'optionalDependencies'):
                k, v = s.split(':', 1); snap[key][f"{k.strip().strip(chr(39))}@{v.strip().strip(chr(39))}"] = 1
    def walk(roots, strict=False):  # strict (prod): an unresolvable prod key is unknown -> fail closed
        seen, st = set(), list(roots)
        while st:
            k = st.pop()
            if k in seen: continue
            seen.add(k)
            if k not in snap:  # alias "foo@bar@1.0.0" -> "bar@1.0.0"; else every snapshot of that name (superset)
                n = nm(k); v = k[len(n) + 1:]
                if v.startswith(('link:', 'file:', 'workspace:')): continue
                if '@' in v[1:]:  # alias "foo@bar@1.0.0": real spec is "bar@1.0.0"
                    if v in snap: st.append(v); continue
                    n = nm(v); v = v[len(n) + 1:]
                if v[:1].isdigit(): hit = [x for x in snap if nm(x) == n]  # resolutions case: every copy (superset)
                else:  # URL/git/tarball: exact version-part match only (never the alias name), plus the real name's other versions
                    hit = [x for x in snap if x[len(nm(x)) + 1:] == v]
                    hit += [x for x in snap if nm(x) in {nm(h) for h in hit}]
                if strict and not hit: raise ValueError(k)
                st += hit
                continue
            st += list(snap[k])
        return {re.sub(r'\(.*$', '', k) for k in seen}
    return walk(imp['prod'], True), walk(imp['dev'])

def npm_v3(path):
    d = json.load(open(path)); prod, dev = set(), set()
    for k, v in d['packages'].items():
        if 'node_modules/' not in k or 'version' not in v: continue
        n = v.get('name') or k.rsplit('node_modules/', 1)[1]
        (dev if v.get("dev") else prod).add(f"{n}@{v['version']}")
    return prod, dev


def scope_sets(path):
    """(prod, dev) sets for a lockfile path, or None (unknown format, missing header, any parse error)."""
    base = os.path.basename(path)
    try:
        if base == 'package-lock.json': return npm_v3(path)
        head = open(path, errors='replace').read(4096)
        if base == 'yarn.lock' and 'yarn lockfile v1' in head: return yarn_v1(path)
        if base == 'pnpm-lock.yaml' and re.search(r"^lockfileVersion: '?9", head, re.M): return pnpm_v9(path)
    except (OSError, ValueError, AttributeError, KeyError, IndexError, TypeError): pass
    return None

def dev_only(path):
    """Set of "name@version" reachable only via devDependencies in the lockfile; empty when unknown."""
    s = scope_sets(path)
    return s[1] - s[0] if s else set()

if __name__ == '__main__':
    for p in sys.argv[1:]:
        for k in sorted(dev_only(p)): print(f'dev\t{k}')
