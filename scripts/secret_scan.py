#!/usr/bin/env python3
"""Secret scanner shared by the privacy gate (scripts/ci-gates.sh) and the rival bench (score_rivals.py).

Python port of the gitleaks default rules, scanning text for live-format secrets. One copy: the gate unions it
with .banlist.txt, the bench scores it as the gitleaks rival, so the two can never drift apart.

Rules are data in gitleaks-v8.30.1.toml next to this file (upstream gitleaks v8.30.1, MIT licence, Copyright (c)
2019 Zachary Rice; pin and sha256 in docs/bench/security-gates-1024/rivals/SOURCES.md). The vendored copy carries `@@`
markers inside public sample Google keys so the privacy gate never fires on it; deleting them restores upstream bytes.

Ported: keyword prefilter, regex, secret group, entropy, rule and global allowlists, `gitleaks:allow` lines.
Not ported: decode-and-rescan of base64/hex/percent, git history; lines are cut to 4 KB before matching. Go RE2 syntax is translated to Python `re`.

CLI (the gate's entry point, fanned out with xargs -P): file paths as arguments (or `--refilter ERE file...`, the banlist half's second pass: prints files with a non-placeholder match (judged on the matched span, not the line)); prints each path that hits (rule id only, never the
secret) and exits 1 on any hit. Files pinned in secret-scan-allow.txt (exact repo-relative path and unchanged sha256) are skipped. Binary files (a NUL byte in the first 8 KB) are skipped, like `grep -I`.
"""
import hashlib, math, pathlib, posixpath, re, subprocess, sys, tomllib

R = pathlib.Path(__file__).resolve().parent

POSIX = {"alnum": "0-9A-Za-z", "alpha": "A-Za-z", "digit": "0-9", "lower": "a-z", "upper": "A-Z", "space": r"\t\n\v\f\r ",
         "punct": r"!-/:-@\[-`{-~", "xdigit": "0-9A-Fa-f", "word": r"0-9A-Za-z_"}


def go2py(p):
    """Translate a Go RE2 pattern to Python re: scoped inline flags, `$`/`\\z` as end-of-text, POSIX classes."""
    out, i, cls, stack = [], 0, False, [0]
    while i < len(p):
        c = p[i]
        if c == "\\":
            out.append(r"\Z" if p[i + 1:i + 2] == "z" else p[i:i + 2]); i += 2; continue
        if cls:
            if p.startswith("[:", i):
                j = p.index(":]", i); out.append(POSIX[p[i + 2:j]]); i = j + 2; continue
            cls = c != "]"; out.append(c); i += 1; continue
        if c == "[":
            cls = True; out.append(c); i += 1
            if p[i:i + 1] == "^": out.append("^"); i += 1
            if p[i:i + 1] == "]": out.append(r"\]"); i += 1
            continue
        if c == "(":
            m = re.match(r"\(\?([imsU]+)\)", p[i:])
            if m: out.append(f"(?{m.group(1)}:"); stack[-1] += 1; i += m.end(); continue
            stack.append(0)
        elif c == ")" and len(stack) > 1:
            out.append(")" * stack.pop())
        elif c == "$":
            out.append(r"\Z"); i += 1; continue
        out.append(c); i += 1
    return "".join(out) + ")" * stack[0]


def entropy(s):
    return -sum(s.count(c) / len(s) * math.log2(s.count(c) / len(s)) for c in set(s)) if s else 0.0


class AL:
    def __init__(s, d):
        c = lambda xs: [re.compile(go2py(x)) for x in xs]
        s.rx, s.paths = c(d.get("regexes", [])), c(d.get("paths", []))
        s.stop, s.rt, s.cond = [w.lower() for w in d.get("stopwords", [])], d.get("regexTarget", ""), d.get("condition", "OR")

    def hit(s, secret, match, line, path):
        t = {"": secret, "secret": secret, "match": match, "line": line}[s.rt]
        ch = ([any(r.search(t) for r in s.rx)] if s.rx else []) + ([any(w in secret.lower() for w in s.stop)] if s.stop else []) \
            + ([any(r.search(path) for r in s.paths)] if s.paths else [])
        return bool(ch) and (all(ch) if s.cond == "AND" else any(ch))


def load_gitleaks():
    cfg = tomllib.loads((R / "gitleaks-v8.30.1.toml").read_text().replace("@@", ""))
    glob = [AL(a) for a in cfg.get("allowlists", [])] + ([AL(cfg["allowlist"])] if "allowlist" in cfg else [])
    rules, fail = [], 0
    for r in cfg["rules"]:
        if "regex" not in r: continue  # path-only rules (file-type rules) do not apply to text strings
        try: rx = re.compile(go2py(r["regex"]))
        except re.error: fail += 1; continue
        pr = re.compile(go2py(r["path"])) if "path" in r else None
        als = [AL(a) for a in r.get("allowlists", [])] + ([AL(r["allowlist"])] if "allowlist" in r else [])
        rules.append((r["id"], rx, [k.lower() for k in r.get("keywords", [])], r.get("secretGroup", 0), r.get("entropy", 0.0), als, pr))
    return glob, rules, fail


GL = load_gitleaks()
LINE_MAX = 4096  # a secret starting past 4 KB of one line (minified bundles) is not seen; the cost of bounded time


# Lines that mark a match as a non-secret: documentation words, filler runs, Stripe test-mode and publishable keys, browser-exposed
# env vars (NEXT_PUBLIC_), Mapbox public tokens, CSRF nonces. Applied to the matched text only (never the rest of the line), only by the gate (precise=True), never to the rival bench.
# client_secret_<type|id|version|...> names hold metadata about a secret, not the secret
CLIENTSECMETA = re.compile(r"(?i)client[_-]?secret[_-]?(?:type|id|version|expir\w*|basic|ref|name|path)\b")
PLACEHOLDER = re.compile(r"(?<![A-Za-z])(?:[Ee]xample|EXAMPLE)(?![a-z]|\.[a-z])|[A-Z0-9]EXAMPLE(?:KEY)?(?![A-Za-z0-9])|(?i:dummy|fake|placeholder|redacted|revoked|replace[_-]?me|changeme|x{8,}|0{10,}|(?<![A-Za-z0-9])[sp]k[_-]test[_-]|pk_live_|next_public_|\bpk\.eyJ|sitekey(?![_-]?(?:secret|private))|(?:captcha|turnstile)[_-]?site[_-]?key(?![_-]?(?:secret|private))|\bcache[_-]?key\b|eyJyb2xlIjoiYW5vbiJ9)|(?<![A-Za-z])your[_-]|dXNlcm5hbWU6cGFzc3dvcmQ|dXNlcjpwYXNz|QWxhZGRpbjpvcGVuIHNlc2FtZQ")

# A CSRF/XSRF token is per-request form state, not a credential; only a name that ENDS in the token name counts (csrf_password and example_password stay judged on their value).
CSRFNAME = re.compile(r"(?i)[\w-]*(?:[cx]srf[_-]?token|csrfmiddlewaretoken)")


def csrf_named(before, text):
    """True when the identifier holding the match start (up to 40 chars before it, plus the match's leading word) ends in a CSRF token name."""
    return bool(CSRFNAME.fullmatch(re.search(r"[\w-]*$", before[-40:]).group() + re.match(r"[\w-]*", text).group()))

# A Google API key whose own line says it is a referrer-restricted public (browser) key is public by design; an unsigned JWT (empty signature) is not a credential.
PUBKEY = re.compile(r"(?i)(?:#|//|--)(?![^\n]*(?:\bnot[ -]|\bun-?|\bnon-?)restricted)[^\n]*?(?:\bpublic\b[^\n]*\b(?:restricted|referr?er)\b|referr?er[- ]restricted|restricted (?:by|to) (?:http )?referr?er)")


def pubkey_ok(tail):
    """True when the text after one match on its line is a comment calling that key public/referrer-restricted and holds no second key."""
    return "AIza" not in tail and bool(PUBKEY.match(tail.lstrip()))


# Perun's own recall rules (gate only: precise=True; the rival bench scores plain gitleaks). (id, regex, secret group, min entropy).
# Added after held-out-4 misses; each passes its decoy twins in scripts/test_secrets_heldout4_blind.py.
_Q = r"""['"](?![$<{%*])"""  # opening quote, not followed by a template/placeholder sigil
# Identifier-shaped values are code references, not secrets: dotted paths and env refs (os.environ[X], config.secret_key_value), snake_case or
# SCREAMING_CASE names, and camelCase words (passwordRequired). Random secrets have no such word structure.
IDENT = re.compile(r"\w+(?:\.\w+)+|[\w.]*[\[\](){}][\w.\[\](){}]*|[a-z]+(?:_[a-z0-9]+)+|[A-Z]+(?:_[A-Z0-9]+)+|[a-z]+(?:[A-Z][a-z]{2,})+\d*", re.A)
# a credential slot that holds only the word for it (curl -u user:PASSWORD) is a template, not a leak
WORDSEC = re.compile(r"(?:YOUR_)?(?:PASSWORD|PASS|SECRET|TOKEN|API_KEY)")  # uppercase only: a lowercase `secret` can be a real password
EXTRA = [(i, re.compile(r), g, e) for i, r, g, e in [
    ("discord-webhook", r"discord(?:app)?\.com/api/webhooks/\d{17,20}/([\w-]{50,})", 1, 3.5),
    ("url-password", r"\b[a-z][a-z0-9+.-]*://[^\s:/]*:(?![^\s@/]*\*\*@)([^\s@/$<>{}%]{8,})@[\w.-]+", 1, 3.0),
    ("secret-key-literal", rf"(?i)secret_key\W{{0,4}}[=:]\s*{_Q}([^'\"\s]{{16,}})['\"]", 1, 3.5),
    ("jwt-literal-secret", rf"\bjwt\.(?:sign|verify)\([^,()]+,\s*{_Q}([^'\"\s]{{16,}})['\"]", 1, 3.0),
    ("google-client-secret", r"\bGOCSPX-[\w-]{20,}", 0, 0),
    ("uuid-credential", r"(?i)\b\w*(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?key|access[_-]?token|auth[_-]?token)\w*=([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\b", 1, 0),
    ("auth-header-token", r"(?i)\bauthorization\W{1,3}(?:bearer|token)\s+([\w.~+/=-]{24,})", 1, 3.5),
    ("password-literal", rf"""(?i)\b\w*(?:password|passwd|_pass)['"]?\s*[=:]\s*['"](?![$<{{%]|\*\*)([^'"\s]{{8,}})['"]""", 1, 3.0),
    ("cli-password", rf"(?i)\b(?:mysql(?:dump)?|psql|sshpass|redis-cli|mongo(?:sh)?)\b[^\n]{{0,200}}?\s-p\s*{_Q}([^'\"\s]{{6,}})['\"]", 1, 3.0),
    ("docker-login-password", r"""(?i)\bdocker\s+login\b[^\n]*?\s(?:-p|--password)[\s=]+['"]?(?![$<{%*-])([^'"\s]{6,})""", 1, 3.0),
    ("telegram-bot-token", r"\b\d{8,10}:(?:AA[\w-]{30,}|[\w-]{35}\b)", 0, 3.0),
    ("sentry-dsn", r"\bhttps://\w{16,}:(\w{16,})@[\w.-]*ingest[\w.-]*/\d+", 1, 3.0),  # legacy key:secret form only; a key-only DSN is public by design
    ("cli-token-flag", r"""(?i)\s--(?:token|api[_-]?key|password|secret)(?:=|\s+)['"]?(?![$<{%*])(?![^\s'"]*/)(?![^\s'"]*\.(?:ya?ml|json|txt|pem|key|env|conf|cfg|ini|toml|crt|p12)(?:[\s'"]|$))([^\s'"]{16,})""", 1, 3.5),
    ("password-assign", r"""(?i)\b(?!test_)\w*passw(?:or)?d(?!\w*(?:length|min|max|policy|_(?:url|uri|link)|(?-i:Url|Uri|URL|URI|Link))\b)\w*['"]?\s*[=:]\s*['"]?(?=[a-z\d])(?!(?:\w*passw(?:or)?d|secret|admin|qwerty|letmein)[\d!]{0,6}(?![^\s'",;]))(?=\S*\d)(?=\S*[a-z])([^\s'",;]{8,})""", 1, 3.0),
    # whitespace-separated forms only where the syntax is fixed: Dockerfile ENV/ARG and netrc `login X password Y`
    ("password-env-netrc", r"""(?i)(?:\b(?:env|arg)\s+\w*passw(?:or)?d\w*|\blogin\s+\S+\s+password)\s+(?=[a-z\d])(?!(?:\w*passw(?:or)?d|secret|admin|qwerty|letmein)[\d!]{0,6}(?![^\s'",;]))(?=\S*\d)(?=\S*[a-z])([^\s'",;]{8,})""", 1, 3.0),
    ("conn-string-password", r"""(?i)[;?&](?:password|pwd)=(?![$<{%*])([^;&\s'"]{8,})""", 1, 3.0),
    ("auth-basic", r"(?i)\bauthorization\W{1,3}basic\s+([A-Za-z0-9+/]{16,}={0,2})", 1, 3.5),
    ("sentry-org-token", r"\bsntry[su]_[\w+/=-]{40,}", 0, 3.5),
    ("fcm-server-key", r"\bAAAA[\w-]{7}:APA91b[\w-]{100,}", 0, 3.5),
    ("twitter-bearer", r"(?i)\b\w*bearer\w*\W{1,4}A{20,}([%\w-]{50,})", 1, 3.5),  # bearer context
    ("twitter-bearer-url", r"\bA{21,}(?!A)(?=[\w-]*%[0-9A-F]{2})([%\w-]{50,})", 1, 3.5),  # no context: 21+ A then a URL-encoded body; a bare base64 blob has no %XX
    # `": "`, `': '`, and a YAML block scalar (`: |` then newline, real or literal `\n`, and indent) all sit between the key and the base64
    ("dockerconfigjson-auth", r"\.dockerconfigjson(?:\W|\\n){1,12}(eyJhdXRocy[A-Za-z0-9+/]{40,}={0,2})", 1, 3.5),
    ("environ-default-secret", r"""(?i)\b(?:environ\.get|getenv)\(\s*['"]\w{0,40}?(?:pass|passwd|password|secret|token|key)\w{0,40}['"]\s*,\s*['"](?![$<{%*]|[a-z]+(?:[-_][a-z]+)+['"]|[^'"\s]*(?:://|arn:))(?=[^'"\s]*\d)([^'"\s]{8,})['"]""", 1, 3.0),  # a hard-coded fallback for a secret-named variable
    ("typed-secret-literal", r"""(?i)\b(?:let|const|static)\s+(?:mut\s+)?\w{0,40}(?:secret|token|api_?key|passw(?:or)?d)\w{0,40}\s*:\s*&?(?:'static\s+)?(?:str|string)\s*=\s*"(?![$<{%*]|[^"\s]*(?:://|arn:))(?=[^"\s]*\d)([^"\s]{16,})\"""", 1, 3.5),  # Rust and TypeScript typed declarations
    ("terraform-variable-default", r"""(?i)\bvariable\s+"(?!\w*(?:_url|_endpoint|_arn|_path|_name|_id)")\w*(?:password|passwd|secret|token|api_?key)\w*"\s*\{(?:[^{}]|\{[^{}]{0,200}\}){0,300}?\bdefault\s*=\s*"(?![$<{%*/]|[^"\s]*(?:://|arn:))(?=[^"\s]*\d)([^"\s]{8,})\"""", 1, 3.0),
    ("k8s-env-value", r"""(?i)\bname:\s*['"]?\w*(?:password|passwd|secret|token|api_?key)\w*['"]?[ \t]*\n\s*value:\s*['"](?![$<{%*]|[^'"\s]*(?:://|arn:))(?=[^'"\s]*\d)([^'"\s]{8,})['"]""", 1, 3.0),
    ("dockerfile-env-secret", r"""(?m)^[ \t]*(?:ENV|ARG)\s+(?i:\w*(?:secret|token|api_?key)\w*)\s+(?![/$.]|\w+://|arn:)(?=\S*\d)(?=\S*[A-Za-z])([\w+/=-]{20,})\s*$""", 1, 3.5),
    ("netrc-password", r"""(?i)\bmachine\s+\S+\s+login\s+\S+\s+password\s+(?![$<{%*])([^\s'",;]{8,})""", 1, 3.0),
    ("pagerduty-key", r"""(?i)pagerduty\w*['"]?\s*[=:]\s*['"]?(u\+[\w-]{18})\b""", 1, 3.0),
    ("mysqli-password", r"""(?i)\bnew\s+mysqli\(\s*['"][^'"]*['"]\s*,\s*['"][^'"]*['"]\s*,\s*['"](?![$<{%*])([^'"\s]{8,})['"]""", 1, 3.0),
    # held-out-9 additions; skipped on purpose: L029 (a service-account private_key_id is an identifier, not the key, and 38 hex is not the real 40), L038 (a sed replacement into a conf file) and L056 (a bare string argument to Session::new) have no shape of their own
    ("resend-key", r"\bre_[A-Za-z0-9]{8}_[A-Za-z0-9]{24}\b", 0, 3.5),
    ("okta-ssws-token", r"\bSSWS\s+(00[\w-]{38,})", 1, 3.5),
    ("cli-password-attached", r"""(?i)\b(?:mysql(?:dump)?|psql|sshpass|redis-cli|mongo(?:sh)?)\b[^\n]{0,200}?\s-p(?![$<{%*'"-])(?=[^'"\s]*\d)([^'"\s]{8,})""", 1, 3.0),
    ("pass-key-assign", r"""(?i)\b[\w-]{0,40}[-_]pass\b['"]?\s*[:=]\s*['"]?(?![$<{%*!])(?=[^\s'",;]*\d)(?=[^\s'",;]*[a-z])([^\s'",;]{8,})""", 1, 3.0),  # ansible_become_pass, ansible-vault-pass
    ("url-query-token", r"""(?i)[?&](?:access[_-]?token|api[_-]?key|auth[_-]?token|client[_-]?secret|private[_-]?token)=(?![$<{%*])(?=[\w.~-]*\d)([\w.~-]{20,})""", 1, 3.0),
    ("xml-add-key-value", r"""(?i)<add\s+key="\w{0,40}(?:key|secret|passw(?:or)?d|token|pwd)\w{0,40}"\s+value="(?![$<{%*])(?=[^"\s]*\d)([^"\s]{20,})\"""", 1, 3.5),
    ("xml-password-element", r"""(?i)<\w{0,20}(?:password|passwd|secret|token)>(?![$<{%*])(?=[^<\s]*\d)([^<\s]{8,})</""", 1, 3.0),
    ("bracket-secret-assign", r"""(?i)\[\s*['"]\w{0,40}(?:secret|passw(?:or)?d|token|(?:api|signing|private|access|auth|encryption|master)_?key)\w{0,40}['"]\s*\]\s*=\s*['"](?![$<{%*/~]|\./|[^'"\s]*(?:://|arn:|\.[a-z]{2,4}['"]))(?=[^'"\s]*\d)([^'"\s]{16,})['"]""", 1, 3.5),  # PHP $config['jwt_secret'], os.environ["SIGNING_KEY"]
    ("vault-token", r"\bhv[sbr]\.([\w-]{24,})", 1, 3.5),
    # held-out-10 additions; skipped on purpose: L009 (a spring.datasource.password of letters only: no digit and no symbol once the corpus marker is removed, so no shape of its own)
    ("php-var-pass", r"""(?i)\$(?!\w{0,20}(?:encrypt|hash|digest|crypt))\w{0,20}pass\b\s*=\s*['"](?![$<{%*])(?=[^'"\s]*\d)(?=[^'"\s]*[a-z])([^'"\s]{8,})['"]""", 1, 3.0),  # $dbpass = "..." (the bare _pass suffix is not matched by password-literal)
    ("wp-key-salt-define", r"""(?i)\bdefine\(\s*['"]\w{0,30}_(?:key|salt)['"]\s*,\s*['"]((?=[^'"\s]*\d)[^'"\s]{32,})['"]""", 1, 3.5),  # WordPress AUTH_KEY, NONCE_SALT
    ("basic-auth-symbol-password", r"""(?i)\bcurl\b[^\n]*?\s(?:-u|--user)[ =]['"]?[\w.@-]{1,40}:(?![$<{%*])(?=[^\s'"]*\d)(?=[^\s'"]*[^\w\s'"])([^\s'"]{8,})""", 1, 3.0),  # gitleaks curl-auth-user stops at a symbol such as !
    ("azure-sas-sig", r"""[?&]sv=\d{4}-\d{2}-\d{2}&[^\s"']{0,300}?\bsig=([^&\s"']{30,})""", 1, 3.5),
    # held-out-11 additions; skipped on purpose: L056 (a bare `pass = ` ini key with 16 letters and no digit: the name collides with the Python keyword and the value has no shape)
    ("slack-webhook-any-host", r"/services/T[A-Z0-9]{8,12}/B[A-Z0-9]{8,12}/([A-Za-z0-9]{24})\b", 1, 3.5),  # gitleaks slack-webhook-url wants hooks.slack.com; proxies and mirrors keep the path
    ("aws-secret-access-key-assign", r"""(?i:aws_secret_access_key)['"]?[\s=:]+['"]?(?=[A-Za-z0-9/+]*\d)(?=[A-Za-z0-9/+]*[a-z])(?=[A-Za-z0-9/+]*[A-Z])([A-Za-z0-9/+]{40})(?![A-Za-z0-9/+=])""", 1, 3.5),  # `aws configure set aws_secret_access_key <40>`, `= <40>`
    ("typed-password-literal", r"""(?i)\b\w*(?:password|passwd|_pass)\s*:\s*[\w.\[\]]+\s*=\s*['"](?![$<{%*])(?=[^'"\s]*\d)([^'"\s]{8,})['"]""", 1, 3.0),  # Python `password: str = "..."`, TypeScript `password: string = "..."`
    ("datadog-key-assign", r"""(?i)\b(?:datadog|dd)_(?:api|app)_key['"]?\s*[=:]\s*['"]?([0-9a-f]{32,40})\b""", 1, 3.0),  # 32-hex API key, 40-hex application key
    ("plaid-secret-assign", r"""(?i)\bplaid_(?:client_)?secret\w{0,10}['"]?\s*[=:]\s*['"]?([0-9a-f]{30})\b""", 1, 3.0),  # Plaid secrets are 30 hex characters
    ("ldap-dn-password", r"""\bldaps?://\w+=[^\s:/@]*:(?![^\s@/]*\*\*@)(?=[^\s@/]*\d)([^\s@/$<>{}%]{8,})@[\w.-]+""", 1, 3.0),  # ldap://cn=admin,dc=acme,dc=com:secret@host (the DN has no `/`; checked for placeholders on the password alone)
    ("redis-cli-auth", r"""(?i)\bredis-cli\b[^\n]*?\s-a\s+['"]?(?![$<{%*'"-])(?=[^'"\s]*\d)([^'"\s]{8,})""", 1, 3.0),  # redis-cli -a PASSWORD (cli-password only knows -p)
    # held-out-12 additions
    ("gcp-sa-private-key-id", r"""(?i)['"]type['"]\s*:\s*['"]service_account['"][^}]{0,600}?['"]private_key_id['"]\s*:\s*['"]([0-9a-f]{40})['"]""", 1, 3.0),  # key id of a service-account JSON (judged on the id alone: a project_id may say "example")
    ("gcp-sa-private-key-id", r"""(?i)['"]private_key_id['"]\s*:\s*['"]([0-9a-f]{40})['"][^}]{0,600}?['"]type['"]\s*:\s*['"]service_account['"]""", 1, 3.0),  # the same with the key before the type
    ("mysql-pwd-assign", r"""(?i)(?<![A-Za-z0-9])mysql_pwd\b['"]?\s*[=:]\s*['"]?(?![$<{%*'"])(?=[^'"\s]*\d)([^'"\s]{8,})""", 1, 3.0),  # MYSQL_PWD=..., the mysql client's password variable
    ("google-refresh-token", r"(?<![\w/])1//0([A-Za-z0-9_-]{40,})(?![\w-])", 1, 3.5),  # Google OAuth refresh token (Firebase CLI, gcloud)
    ("flyio-token", r"(?<![A-Za-z0-9])fm[12][ar]?_([A-Za-z0-9+/=_-]{40,})", 1, 3.5),  # Fly.io token (FlyV1 fm2_..., fm1_, fm1r_), under any name and without the gitleaks 100-char floor
    # held-out-14 additions; excluded on purpose (logged in the corpus ledger): L017 (a service-account private_key_id is an identifier, not the key), L033 (a key-only Sentry DSN is public by design), L060 (a pass-named bare token with no assignment; false-positive risk judged too high, accepted miss)
    ("nuget-cleartext-password", r"""(?i)\bClearTextPassword['"]?\s+value\s*=\s*['"](?![$<{%*])([^'"\s]{8,})['"]""", 1, 3.0),  # nuget.config <add key="ClearTextPassword" value="...">; letters-only values slip password-assign
    ("nuget-cleartext-password", r"""(?i)\bvalue\s*=\s*['"](?![$<{%*])([^'"\s]{8,})['"]\s+key\s*=\s*['"]ClearTextPassword['"]""", 1, 3.0),  # attributes in the other order
    ("sas-sig-last", r"""\bs[epv]=[\w%:.+-]+&(?:[\w%:.+/=-]+&){0,6}sig=([A-Za-z0-9%+/]{40,})""", 1, 3.5),  # sig as a late parameter without sv
    ("sas-sig-first", r"""\bsig=([A-Za-z0-9%+/]{40,})(?=[^\s"']*&s[epv]=)""", 1, 3.5),  # Azure SAS with sig before se/sp/sv (azure-sas-sig needs sv first)
    ("client-secret-assign", r"""(?i)\b\w*client[_-]?secret(?:[_-]?(?:value|key))?['"]?\s*[=:]\s*['"]?(?![$<{%*])(?![^'"\s]*://)(?=[\w~.+/=-]*\d)(?=[\w~.+/=-]*[a-z])(?=[\w~.+/=-]*[A-Z])([\w~.+/=-]{30,})""", 1, 3.5),  # AZURE_CLIENT_SECRET, OAuth client secrets; not client_secret_name/_path/_ref, Key Vault or SOPS refs
    ("stripe-webhook-secret", r"\bwhsec_([A-Za-z0-9]{32,})", 1, 3.5),
    ("doppler-token", r"\bdp\.(?:pt|st|sa|ct|scim|audit)(?:\.[\w-]{1,60}){0,2}?\.([A-Za-z0-9]{40,44})\b", 1, 3.5),  # dp.st.<config>.<40>; gitleaks knows only dp.pt.
    ("piped-login-password", r"""(?i)(?:\b(?:echo|printf)\s+(?:-[ne]+\s+)?(?:['"]?%s\s*['"]?\s+)?|\bcat\s+<<<\s*)['"]?(?![$<{%*'"-])(?!(?:[a-z]{3,}-){3})(?=[^'"\s|]*\d)(?=[^'"\s|]*[a-z])([^'"\s|]{20,})['"]?\s*\|(?:[^\n|]*\|)*?\s*[^\n|]*?\blogin\b[^\n]*--(?:password-stdin|with-token)""", 1, 3.5),  # echo/printf/here-string piped into docker/gh login
    ("piped-login-password", r"""(?i)\blogin\b[^\n]*--(?:password-stdin|with-token)\s*<<<\s*['"]?(?![$<{%*'"-])(?!(?:[a-z]{3,}-){3})(?=[^'"\s|]*\d)(?=[^'"\s|]*[a-z])([^'"\s|]{20,})""", 1, 3.5),
    # held-out-15 additions; skipped on purpose: none (all twelve blind misses have a real credential shape or an explicit secret-declaring name/flag)
    ("cli-flag-password-quoted", r"""(?i)\b(?:snowsql|sshpass|mysql(?:dump)?|mongo(?:sh)?)\b[^\n]{0,200}?\s-p\s*(['"])(?![$<{*'-]|%[sd({])(?=[^'"\n]*[^A-Za-z'"\s])([^'"\n]{8,})\1""", 2, 3.0),  # quoted `-p` values may hold spaces
    ("cli-flag-password-quoted", r"""(?i)\b(?:snowsql|sshpass|mysql(?:dump)?|mongo(?:sh)?)\b[^\n]{0,200}?\s-p\s*['"]?(?![$<{*'"-]|%[sd({])(?=[^'"\s]*[^A-Za-z'"\s])([^'"\s]{8,})""", 1, 3.0),  # `sshpass -p 'pw'`, `snowsql -p pw`: a port is at most 5 digits, so 8+ chars with a digit or symbol is a password (cli-password-attached skips quotes)
    ("cli-flag-password-quoted", r"""(?i)\bsshpass\b[^\n]{0,200}?\s-p\s*['"]?(?![$<{*'"-]|%[sd({])([^'"\s]{8,})""", 1, 3.0),  # sshpass -p is always the password, so letters-only counts there; for mysql/snowsql/mongosh a letters-only `-p name` stays unflagged (could be a database name)
    ("figma-pat", r"(?<![A-Za-z0-9])figd_([A-Za-z0-9_-]{36,})", 1, 3.5),  # Figma personal access token
    ("launchdarkly-key", r"(?<![A-Za-z0-9])(?:sdk|mob)-((?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})|[0-9a-f]{32,40})(?![\w-])", 1, 3.0),  # LaunchDarkly server SDK / mobile key (client-side IDs have no prefix and are public)
    ("authorization-apikey", r"""(?<![A-Za-z0-9])(?i:ApiKey)\s+['"]?(?![$<{%*'"])(?=[A-Za-z0-9+/_-]*\d)(?=[A-Za-z0-9+/_-]*[a-z])(?=[A-Za-z0-9+/_-]*[A-Z])([A-Za-z0-9+/_-]{40,}={0,2})""", 1, 3.5),  # Elasticsearch `Authorization: ApiKey <base64 id:key>`; the HTTP scheme is case-insensitive, the value is not
    ("laravel-app-key", r"""(?<![A-Za-z0-9])(?:APP_KEY|app[_.]key|['"]key['"][ \t]{0,8}=>)['"]?[ \t]{0,8}[=:]?[ \t]{0,8}['"]?base64:([A-Za-z0-9+/]{43}=)""", 1, 3.5),  # Laravel APP_KEY: base64 of 32 random bytes (44 chars); an empty or `base64:` stub is not matched; bounded gaps keep it linear
    ("openssl-pass-arg", r"""(?i)\s-pass(?:in|out)?[ =]\s*['"]?pass:['"]?(?![$<{%*'"])([^'"\s]{8,})""", 1, 3.0),  # openssl -pass pass:<literal> (env:, file: and stdin forms are references); the flag itself says secret, so no digit needed
    ("openssl-pass-arg", r"""(?i)\bopenssl\b[^\n]{0,200}?\s-k\s+['"]?(?![$<{%*'"-])([^'"\s]{8,})""", 1, 3.0),  # openssl enc -k <literal passphrase>
    ("passphrase-flag", r"""(?i)--passphrase(?:[ =]\s*|\s+)(['"])(?![$<{%*-])([^'"\n]{8,})\1""", 2, 2.9),  # gpg --passphrase with a quoted value that holds spaces; entropy 2.9 so an 8-distinct-digit run counts
    ("passphrase-flag", r"""(?i)--passphrase(?:[ =]\s*|\s+)(?![$<{%*'"-])([^'"\s]{8,})""", 1, 2.9),  # gpg --passphrase <literal>; --passphrase-file/-fd do not match
    ("tf-variable-secret-default", r"""(?i)\bvariable\s+['"](?!\w*(?:_url|_endpoint|_arn|_path|_name|_id)['"])\w{0,30}(?:password|passwd|secret|token|api_?key|_pass)\w{0,20}['"]\s*\{(?:[^{}]|\{[^{}]{0,200}\}){0,300}?\bdefault\s*=\s*['"](?![$<{%*/]|arn:|https?:)(?=[^'"\s]*[^A-Za-z'"\s])([^'"\s]{8,})['"]""", 1, 3.0),  # Terraform variable "db_password" { default = "..." } ships the secret in the repo; metadata names (_url, _arn, ...) and arn/URL/path values are not secrets; one nested block (validation {}) is skipped
    ("cfn-noecho-default", r"""(?im)(?:^([ \t]*))?['"]?NoEcho['"]?\s*:\s*['"]?true['"]?(?:[ \t,]+|(?:[ \t]*,[ \t]*['"]?(?!Default\b|NoEcho\b)\w+['"]?[ \t]*:[^,\n]{1,60}){1,3}[ \t]*,[ \t]*|[ \t,]*(?:\#[^\n]*)?\r?(?:\n\1(?![ \t]*['"]?(?:NoEcho|Default)\b)[^\n]*){0,3}?\n\1)['"]?Default['"]?\s*:\s*['"]?(?![$<{%*'"!])(?=[^'"\s,}]*\d)([^'"\s,}]{8,})""", 2, 3.0),  # CloudFormation parameter declared NoEcho (a secret) with a literal Default; multi-line keys must be siblings (same indent); a trailing YAML comment, CRLF and up to 3 same-line JSON keys in between are allowed
    ("cfn-noecho-default", r"""(?im)(?:^([ \t]*))?['"]?Default['"]?\s*:\s*['"]?(?![$<{%*'"!])(?=[^'"\s,}]*\d)([^'"\s,}]{8,})['"]?(?:[ \t,]+|(?:[ \t]*,[ \t]*['"]?(?!Default\b|NoEcho\b)\w+['"]?[ \t]*:[^,\n]{1,60}){1,3}[ \t]*,[ \t]*|[ \t,]*(?:\#[^\n]*)?\r?(?:\n\1(?![ \t]*['"]?(?:NoEcho|Default)\b)[^\n]*){0,3}?\n\1)['"]?NoEcho['"]?\s*:\s*['"]?true""", 2, 3.0),  # the same with Default first
    ("securestring-plaintext", r"""(?i)\bConvertTo-SecureString\s+(?:-String\s+)?['"](?![$<{%*])([^'"\n]{8,})['"]\s+(?:-Force\s+)?-AsPlainText""", 1, 3.0),  # PowerShell ConvertTo-SecureString "literal" -AsPlainText -Force; the flag itself says plaintext, so letters-only and spaced literals count
    ("securestring-plaintext", r"""(?i)['"](?![$<{%*])([^'"\n]{8,})['"]\s*\|\s*ConvertTo-SecureString\b[^\n]*-AsPlainText""", 1, 3.0),  # piped / here-string order
    ("securestring-plaintext", r"""(?i)\bConvertTo-SecureString\b[^\n]{0,200}?-AsPlainText\s+(?:-Force\s+)?(?:-String\s+)?['"](?![$<{%*])([^'"\n]{8,})['"]""", 1, 3.0),  # -AsPlainText before the literal
    ("named-token-literal", r"""(?i)\b\w{0,20}(?:api|auth|access|bearer|secret|private|signing)[_-]?(?:token|key|secret)\b['"]?\s*[=:]\s*['"](?![$<{%*/~]|AIza)(?=[^'"\s]*\d)(?=[^'"\s]*[a-z])(?=[^'"\s]*[A-Z])([\w.=-]{32,})['"]""", 1, 3.8),  # const apiToken = "tk_<random>" (gitleaks generic-api-key drops it through its stopword list)
]]


def gitleaks_rule(text, path="input.txt", precise=False):
    """Return the ids of every rule that flags text (scanned as a file body at `path`); empty means clean.

    precise=True also drops matches whose own text looks like a placeholder or public-by-design value (PLACEHOLDER); the gate sets it, the bench does not."""
    glob, rules, _ = GL
    frag = "\n".join(l[:LINE_MAX] for l in text.split("\n")) + "\n"; low = frag.lower(); out = []  # long lines make the regexes quadratic
    for rid, rx, kw, sg, ent, als, pr in rules:
        if (kw and not any(k in low for k in kw)) or (pr and not pr.search(path)): continue
        for m in rx.finditer(frag):
            line = frag[frag.rfind("\n", 0, m.start()) + 1:frag.find("\n", m.end())]
            gs = [g for g in m.groups() if g]
            sec = m.group(sg) or "" if sg else (gs[0] if gs else m.group(0))
            if "gitleaks:allow" in line or (precise and (PLACEHOLDER.search(m.group(0)) or csrf_named(frag[:m.start()], m.group(0)) or ((rid == "generic-api-key" and CLIENTSECMETA.search(m.group(0))) or (rid == "gcp-api-key" or (rid == "generic-api-key" and sec.startswith("AIz"))) and pubkey_ok(frag[m.end():frag.find("\n", m.end())])) or (rid == "jwt" and sec.endswith(".")) or WORDSEC.fullmatch(sec.rpartition(":")[2]))): continue
            if ent and entropy(sec) <= ent: continue
            if any(a.hit(sec, m.group(0), line, path) for a in glob + als): continue
            out.append(rid); break
    xf = frag.replace("\\n", "\n")  # a literal backslash-n (JSON, logs, one-line fixtures) is a line break for the extra rules
    for rid, rx, g, ent in EXTRA if precise else ():
        for m in rx.finditer(xf):
            if not csrf_named(xf[:m.start()], m.group(0)) and not PLACEHOLDER.search(m.group(g) if rid in ("ldap-dn-password", "gcp-sa-private-key-id") else m.group(0)) and entropy(m.group(g)) > ent and not (g and IDENT.fullmatch(m.group(g))) and "gitleaks:allow" not in xf[xf.rfind("\n", 0, m.start()) + 1:xf.find("\n", m.end())]:
                out.append(rid); break
    return out


def _allowed(f, allow):
    """True if f's path relative to its git top-level equals an allow-list entry exactly and its sha256 still matches the pin."""
    try:
        d = pathlib.Path(f).resolve().parent
        top = pathlib.Path(subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()).resolve()
        rel = pathlib.Path(f).resolve().relative_to(top).as_posix()
        return allow.get(rel) == hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def refilter(pat, files):
    """Print each file where ERE `pat` matches a line that is not a placeholder; unverifiable files (bad regex, no Python match, unreadable) are kept (fail closed)."""
    try: rx = re.compile(go2py(pat))
    except re.error: rx = None
    for f in files:
        try: lines = pathlib.Path(f).read_text("utf-8", "replace").split("\n")
        except OSError: lines = None
        if rx is None or lines is None or not any(rx.search(l) for l in lines) or any(not (PLACEHOLDER.search(m.group(0)) or csrf_named(l[:m.start()], m.group(0))) and not (m.group(0).startswith("AIza") and pubkey_ok(l[m.end():])) for l in lines for m in rx.finditer(l)): print(f)


def main(argv):
    """Scan the files named in argv; exit 1 on any hit, 2 on an unreadable file or a bad rule (fail closed)."""
    if argv[:1] == ["--refilter"]: refilter(argv[1], argv[2:]); return 0
    if GL[2]: print(f"secret_scan: {GL[2]} gitleaks regexes failed to compile", file=sys.stderr); return 2
    allow = {l.split(None, 1)[1]: l.split()[0] for l in (R / "secret-scan-allow.txt").read_text().splitlines() if l and not l.startswith("#")}
    names = {posixpath.basename(a) for a in allow}
    hit = 0
    for f in argv:
        if posixpath.basename(f) in names and _allowed(f, allow): continue
        try: b = pathlib.Path(f).read_bytes()
        except OSError as e: print(f"secret_scan: cannot read {f}: {e.strerror}", file=sys.stderr); return 2
        if b"\0" in b[:8192]: continue
        ids = gitleaks_rule(b.decode("utf-8", "replace"), f, True)
        if ids: print(f"  {f} ({', '.join(ids)})"); hit = 1
    return hit


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
