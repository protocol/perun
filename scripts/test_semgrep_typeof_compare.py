#!/usr/bin/env python3
"""Regression test: a `typeof x !== "string"` type check is never a hardcoded-credential compare (js.yml).

Semgrep binds `$X` / `$T` to the whole operand, so `typeof req.body.password !== "string"` hands the name regex the text
"typeof req.body.password", whose tail looks like a credential name. This test applies the rules' own metavariable regexes to
the bound text (Python `re`, no semgrep needed), so it runs offline and the same in CI. JS_YML=<file> checks another copy of the
rules (used to show the cases fail before the fix). Plain asserts."""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.environ.get("JS_YML") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint", "js.yml")
SRC = open(JS).read()


def flagged(rule, mv, text):
    """True when every metavariable-regex of `rule` on `mv` accepts `text`, which is when semgrep reports the match."""
    blk = SRC.split(f"- id: perun.js.{rule}\n")[1].split("\n- id:")[0]
    rx = re.findall(rf"metavariable: \${mv}\n\s+regex: (.*)", blk)
    assert rx, (rule, mv)
    return all(re.search(r, text) for r in rx)


CRED, BASIC = "hardcoded-credential-compare", "hardcoded-basic-auth"
for t in ("typeof req.body.password", "typeof config.apiKey", "typeof this.authToken", "typeof user.secret", "typeof body['token']",
          "typeof password", "typeof(req.body.password)"):
    assert not flagged(CRED, "X", t), f"type check flagged as credential compare: {t}"
for t in ("req.body.password", "config.apiKey", "this.authToken", "user.secret", "body['token']", "password.toLowerCase()",
          "typeofToken", "typeof_secret"):  # a name that merely starts with typeof is still a credential name
    assert flagged(CRED, "X", t), f"credential compare no longer flagged: {t}"
assert not flagged(BASIC, "T", "typeof decoded") and not flagged(BASIC, "T", "typeof(creds)")
assert flagged(BASIC, "T", "decoded") and flagged(BASIC, "T", "creds") and flagged(BASIC, "T", "typeofCreds")
print("ok")
