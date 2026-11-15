#!/usr/bin/env python3
"""mcp_config_check.py - lead-finder for risky agent and MCP config.

Usage: python3 -I mcp_config_check.py < paths   (one path per line; non-config paths are ignored)

Reads .mcp.json, .cursor/mcp.json, .vscode/mcp.json and .claude/settings*.json. Rows, TSV `file<TAB>line<TAB>rule<TAB>message`, stdlib only:
- mcp-unpinned: a server command that fetches a package at run time with no version (npx, bunx, pnpm dlx, uvx; `@latest` counts as unpinned).
- mcp-insecure-url: a server url using http:// to a host that is not localhost.
- mcp-literal-secret: a secret-named env or headers value that is a literal, not a ${VAR} reference. The message never echoes the value.
- agent-broad-allow: a permissions.allow rule of `*`, `Bash` or `Bash(*)`.
- hook-pipe-shell: a hook command that pipes curl or wget into a shell.
- not-checked: a file that could not be read or parsed.
Line numbers point at the first line holding the offending text (1 when not found). A lead, confirm it in the file.
"""
import json
import re
import sys
from urllib.parse import urlparse

CFG = re.compile(r"(^|/)(\.mcp\.json|\.cursor/mcp\.json|\.vscode/mcp\.json|\.claude/settings[^/]*\.json)$")
RUNNERS = {"npx", "bunx", "uvx"}
SECRET = re.compile(r"key|token|secret|passw|auth|credential|bearer", re.I)
REF = re.compile(r"\$\{|^\$\w+$")
PIPE = re.compile(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")


def unpinned(cmd, args):
    toks = [cmd] + [a for a in args if isinstance(a, str)]
    if toks[0] == "pnpm" and toks[1:2] == ["dlx"]:
        toks = ["pnpm-dlx"] + toks[2:]
    elif toks[0] not in RUNNERS:
        return None
    pkg = next((a for a in toks[1:] if not a.startswith("-")), None)
    if not pkg:
        return None
    ver = re.sub(r"^@", "", pkg).partition("@")[2] or pkg.partition("==")[2]
    return pkg if ver in ("", "latest") else None


def scan(path, text):
    try:
        doc = json.loads(text)
    except ValueError as e:
        return [(path, 1, "not-checked", "invalid JSON: %s" % e)]
    lines = text.splitlines()
    rows = []

    def row(needle, rule, msg):
        n = next((i + 1 for i, s in enumerate(lines) if needle in s), 1)
        rows.append((path, n, rule, msg))

    for key in ("mcpServers", "servers"):
        servers = doc.get(key) if isinstance(doc, dict) else None
        for name, s in (servers.items() if isinstance(servers, dict) else []):
            if not isinstance(s, dict):
                continue
            cmd, args = s.get("command"), s.get("args") or []
            pkg = unpinned(cmd, args) if isinstance(cmd, str) and isinstance(args, list) else None
            if pkg:
                row(pkg, "mcp-unpinned", "server %s runs %s %s with no pinned version: fetched at run time, a new release runs unreviewed" % (name, cmd, pkg))
            url = s.get("url")
            if isinstance(url, str) and url.startswith("http://") and urlparse(url).hostname not in ("localhost", "127.0.0.1", "::1"):
                row(url, "mcp-insecure-url", "server %s url is plain http to a non-local host" % name)
            for field in ("env", "headers"):
                for k, v in (s.get(field) or {}).items() if isinstance(s.get(field), dict) else []:
                    if isinstance(v, str) and v and SECRET.search(k) and not REF.search(v):
                        row('"%s"' % k, "mcp-literal-secret", "server %s %s %s holds a literal value, use a ${VAR} reference" % (name, field, k))
    perms = doc.get("permissions") if isinstance(doc, dict) else None
    for r in (perms.get("allow") or []) if isinstance(perms, dict) and isinstance(perms.get("allow"), list) else []:
        if r in ("*", "Bash", "Bash(*)"):
            row(json.dumps(r), "agent-broad-allow", "permissions.allow %s lets the agent run anything without asking" % r)

    def hooks(o):
        if isinstance(o, dict):
            c = o.get("command")
            if isinstance(c, str) and PIPE.search(c):
                row(c[:40], "hook-pipe-shell", "a hook pipes a download into a shell")
            for v in o.values():
                hooks(v)
        elif isinstance(o, list):
            for v in o:
                hooks(v)
    if isinstance(doc, dict):
        hooks(doc.get("hooks"))
    return rows


def main():
    for p in sys.stdin.read().split("\n"):
        if not CFG.search(p):
            continue
        try:
            text = open(p, encoding="utf-8").read()
        except (OSError, ValueError) as e:
            print("%s\t1\tnot-checked\tunreadable: %s" % (p, type(e).__name__), flush=True)
            continue
        for r in scan(p, text):
            print("%s\t%d\t%s\t%s" % r, flush=True)


if __name__ == "__main__":
    main()
