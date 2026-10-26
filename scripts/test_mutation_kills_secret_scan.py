#!/usr/bin/env python3
"""In-process pins for scripts/secret_scan.py (go2py, entropy, AL, csrf_named, pubkey_ok, gitleaks_rule, _allowed, refilter, main),
written to kill the mutants scripts/mutation_safety.py found alive. Tokens are built at runtime from a hash, so no literal secret sits
in this file. Run: python3 scripts/test_mutation_kills_secret_scan.py (or pytest). Offline; temp files and one temp git repo only."""
import contextlib, hashlib, io, os, pathlib, subprocess, sys, tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import secret_scan as ss  # noqa: E402

A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
U = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def tok(seed, n, al=A):
    h = hashlib.sha256(seed.encode()).digest() * 4
    return "".join(al[b % len(al)] for b in h)[:n]


GHP = "ghp_" + tok("g", 36)
AWS = "AKIA" + tok("a", 16, U)
STRIPE = "sk_live_" + tok("s", 24)
GCP = "AIza" + tok("gc", 35, A + "_-")
JWT = "eyJ" + tok("j1", 20) + ".eyJ" + tok("j2", 20) + "." + tok("j3", 30)


def test_go2py():
    for src, want in [(r"a$", r"a\Z"), (r"\z", r"\Z"), (r"\\z", r"\\z"), (r"[a$]", "[a$]"), ("[[:digit:][:upper:]]", "[0-9A-Z]"), ("(a)(?i)b", "(a)(?i:b)"),
                      ("(?is)x(y)", "(?is:x(y))"), ("[]a]", r"[\]a]"), ("[^]a]x", r"[^\]a]x"), ("a)", "a)"), ("(?s)", "(?s:)"), (r"\(", r"\("),
                      (r"[\]]x", r"[\]]x"), ("(?i)a(b)c", "(?i:a(b)c)"), ("a(b(?i)c)d", "a(b(?i:c))d"), (r"(?i)foo[[:alnum:]_]+\z$", r"(?i:foo[0-9A-Za-z_]+\Z\Z)"),
                      ("[[:space:]]", r"[\t\n\v\f\r ]"), ("[a-c[:xdigit:]]", "[a-c0-9A-Fa-f]"), ("", "")]:
        assert ss.go2py(src) == want, (src, ss.go2py(src))


def test_entropy():
    assert ss.entropy("") == 0.0 and ss.entropy("aaaa") == 0 and ss.entropy("ab") == 1.0 and ss.entropy("abcd") == 2.0
    assert abs(ss.entropy("aab") - 0.9182958340544896) < 1e-12


def test_allowlist_AL():
    h = lambda d, s="sec", m="match", l="line", p="path": ss.AL(d).hit(s, m, l, p)
    assert not h({}) and not h({"condition": "AND"})
    assert h({"regexes": ["se"]}) and not h({"regexes": ["zz"]}) and h({"regexes": ["zz", "e"]})
    assert h({"regexes": ["^mat"], "regexTarget": "match"}) and not h({"regexes": ["^mat"]}) and not h({"regexes": ["^mat"], "regexTarget": "line"})
    assert h({"regexes": ["^li"], "regexTarget": "line"}) and h({"regexes": ["^sec$"], "regexTarget": "secret"}) and h({"regexes": ["^sec$"], "regexTarget": ""})
    assert h({"stopwords": ["SE"]}) and h({"stopwords": ["x", "ec"]}) and not h({"stopwords": ["xx"]}) and h({"stopwords": ["ec"]}, s="SEC")
    assert h({"paths": ["^pa"]}) and not h({"paths": ["^zz"]})
    both = {"regexes": ["se"], "stopwords": ["xx"]}
    assert h(both) and not h({**both, "condition": "AND"}) and h({"regexes": ["se"], "stopwords": ["ec"], "condition": "AND"})
    assert not h({"regexes": ["se"], "stopwords": ["ec"], "paths": ["zz"], "condition": "AND"}) and h({"regexes": ["se"], "stopwords": ["ec"], "paths": ["zz"]})
    try:
        h({"regexes": ["x"], "regexTarget": "bogus"})
    except KeyError:
        pass
    else:
        raise AssertionError("bad regexTarget accepted")
    a = ss.AL({"stopwords": ["Foo"], "regexTarget": "line", "condition": "AND"})
    assert a.stop == ["foo"] and a.rt == "line" and a.cond == "AND" and ss.AL({}).rt == "" and ss.AL({}).cond == "OR"


def test_csrf_named():
    c = ss.csrf_named
    for b, t in [("x csrf_", "token"), ("csrf_token", ""), ("y" * 50 + "xsrftoken", ""), ("CSRF-TOKEN", ""), ("a-csrf", "-token"), ("z" * 39 + "csrf_tok", "en"),
                 ("csrfmiddlewaretoken", "")]:
        assert c(b, t), (b, t)
    for b, t in [("csrf_token ", "x"), ("csrf_token", "abc"), ("csrf_password", ""), ("", "x"), ("csrfmiddlewaretoken", "Q"), ("z" * 41 + "csrf_tok", "x")]:
        assert not c(b, t), (b, t)


def test_pubkey_ok():
    for t in ["  // public key, referrer restricted", "# referrer-restricted", "# restricted to referrer", "-- restricted by http referer", "\n# public referrer",
              "#public referrer"]:
        assert ss.pubkey_ok(t), t
    for t in ["# un-restricted public referrer", "# non-restricted public key referrer", "# not restricted, public referrer", "// public", "public referrer restricted",
              "# public key restricted AIzaXX", "", "plain"]:
        assert not ss.pubkey_ok(t), t


def test_gitleaks_rule_basics():
    g = ss.gitleaks_rule
    assert g(GHP) == ["github-pat"] and g(GHP, precise=True) == ["github-pat"] and g(f"t = {GHP}\n") == ["github-pat"]
    assert "aws-access-token" in g(AWS) and g(STRIPE) == ["stripe-access-token"] and g("-----BEGIN RSA PRIVATE KEY-----\n" + tok("p", 64) + "\n-----END RSA PRIVATE KEY-----") == ["private-key"]
    assert g("") == [] and g("nothing here") == [] and g("x = ghp_" + "ab" * 18) == []  # below the rule's entropy floor
    assert g(f"{GHP}  # gitleaks:allow") == [] and g(f"line1\n{GHP} gitleaks:allow") == [] and g(f"gitleaks:allow\n{GHP}") == ["github-pat"]
    assert g("x" * 5000 + " " + GHP) == [] and g("x" * 4000 + " " + GHP) == ["github-pat"]  # a line is cut at 4 KB
    assert g("a\n" + "x" * 5000 + "\n" + GHP) == ["github-pat"]
    assert g(GHP, "package-lock.json") == [] and g(GHP, "pnpm-lock.yaml") == [] and g(GHP, "x.txt") == ["github-pat"]  # global path allowlist
    assert g("key = " + AWS[:12] + "EXAMPLE") == []  # AKIA...EXAMPLE has the wrong shape for the rule either way
    assert g(f"x {STRIPE.replace('sk_live_', 'sk_test_')}") == ["stripe-access-token"] and g("x " + STRIPE.replace("sk_live_", "sk_test_"), precise=True) == []
    assert g("t = " + JWT) == ["jwt"] and g("t = " + JWT, precise=True) == ["jwt"] and g("t = " + JWT.rsplit(".", 1)[0] + ".", precise=True) == []
    assert g("t = " + JWT.rsplit(".", 1)[0] + ".") == ["jwt"]
    assert g("k = " + GCP) == ["gcp-api-key"] and g("k = " + GCP, precise=True) == ["gcp-api-key"]
    assert g("k = " + GCP + "  // public key, referrer restricted", precise=True) == [] and g("k = " + GCP + "  // public key, referrer restricted") == ["gcp-api-key"]
    assert g("k = " + GCP + "  // public key, not restricted", precise=True) == ["gcp-api-key"]


def test_gitleaks_rule_extra_rules_are_gate_only():
    pw = 'db_password = "' + tok("pw", 16) + '"'
    assert "password-literal" not in ss.gitleaks_rule(pw) and "password-literal" in ss.gitleaks_rule(pw, precise=True)
    assert ss.gitleaks_rule(pw.replace(tok("pw", 16), "your_password_here_please"), precise=True) == []
    env = "ENV MY_TOKEN " + tok("e", 32)
    assert ss.gitleaks_rule(env, precise=True) == ["dockerfile-env-secret"] and ss.gitleaks_rule(env) == []
    assert ss.gitleaks_rule("FROM x\\n" + env, precise=True) == ["dockerfile-env-secret"]  # a literal backslash-n is a line break
    assert "password-literal" not in ss.gitleaks_rule(pw + "  # gitleaks:allow", precise=True)
    assert ss.gitleaks_rule("ENV MY_TOKEN " + "ab" * 16, precise=True) == []  # low entropy
    assert ss.gitleaks_rule("ENV MY_TOKEN dummy" + tok("e", 32), precise=True) == []  # placeholder word
    gc = "GOOGLE_CLIENT_SECRET=GOCSPX-" + tok("g", 28)
    assert "google-client-secret" in ss.gitleaks_rule(gc, precise=True) and "google-client-secret" not in ss.gitleaks_rule(gc)
    ident = "secret_key = '" + "config_secret_key_value_long_name" + "'"
    assert "secret-key-literal" not in ss.gitleaks_rule(ident, precise=True)  # identifier-shaped value
    wc = "mysql -u root -p'" + tok("m", 16) + "' -h db.acme.example.com"
    assert "cli-password" in ss.gitleaks_rule(wc, precise=True)


def test_allowed_pin():
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
        r = pathlib.Path(t).resolve()
        subprocess.run(["git", "init", "-q", str(r)], check=True)
        (r / "sub").mkdir()
        f = r / "sub" / "a.txt"
        f.write_text("hello\n")
        sha = hashlib.sha256(b"hello\n").hexdigest()
        assert ss._allowed(str(f), {"sub/a.txt": sha}) is True
        assert ss._allowed(str(f), {"a.txt": sha}) is False and ss._allowed(str(f), {}) is False and ss._allowed(str(f), {"sub/a.txt": "0" * 64}) is False
        f.write_text("changed\n")
        assert ss._allowed(str(f), {"sub/a.txt": sha}) is False
        assert ss._allowed(str(r / "missing.txt"), {"missing.txt": sha}) is False
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:  # not a git checkout
        p = pathlib.Path(t) / "b.txt"
        p.write_text("hello\n")
        assert ss._allowed(str(p), {"b.txt": sha}) is False


def run_refilter(pat, files):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ss.refilter(pat, files)
    return out.getvalue().split()


def test_refilter():
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
        d = pathlib.Path(t)
        mk = lambda n, s: str(d / n) if (d / n).write_text(s) else str(d / n)
        real, ph, none, mixed = mk("real", f"x\nkey {AWS}\n"), mk("ph", "key AKIAIOSFODNN7EXAMPLE\n"), mk("none", "nothing\n"), mk("mixed", f"AKIAIOSFODNN7EXAMPLE\n{AWS}\n")
        pub = mk("pub", f"k = {GCP}  # public key, referrer restricted\n")
        pubnot = mk("pubnot", f"k = {GCP}  # not restricted\n")
        csrf = mk("csrf", f"csrf_token={GHP}\n")
        missing = str(d / "missing")
        pat = "AKIA[0-9A-Z]{16}"
        assert run_refilter(pat, [real, ph, none, mixed, missing]) == [real, none, mixed, missing]
        assert run_refilter("AIza[0-9A-Za-z_-]{35}", [pub, pubnot]) == [pubnot]
        assert run_refilter(r"\w+=ghp_[A-Za-z0-9]{36}", [csrf, mk("csrf2", f"x={GHP}\n")]) == [str(d / "csrf2")]
        assert run_refilter("(", [ph]) == [ph]  # unverifiable pattern: fail closed
        assert run_refilter(pat, []) == [] and run_refilter(pat, [ph, ph]) == []


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ss.main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_main():
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
        d = pathlib.Path(t).resolve()
        old_r, old_gl = ss.R, ss.GL
        (d / "secret-scan-allow.txt").write_text("# pins\n\n")
        ss.R = d
        try:
            clean, bad, binf = d / "clean.txt", d / "bad.txt", d / "bin.dat"
            clean.write_text("nothing here\n")
            bad.write_text(f"t = {GHP}\n")
            binf.write_bytes(b"\0" + GHP.encode())
            assert run_main([str(clean)]) == (0, "", "") and run_main([]) == (0, "", "") and run_main([str(binf)]) == (0, "", "")
            assert run_main([str(bad)]) == (1, f"  {bad} (github-pat)\n", "")
            assert run_main([str(clean), str(bad), str(clean)])[:2] == (1, f"  {bad} (github-pat)\n")
            dup = d / "dup.txt"
            dup.write_text(f"{GHP}\n{STRIPE}\n")
            rc, out, _ = run_main([str(dup)])
            assert rc == 1 and out == f"  {dup} (github-pat, stripe-access-token)\n"
            rc, out, err = run_main([str(clean), str(d / "nope"), str(bad)])
            assert rc == 2 and out == "" and err == f"secret_scan: cannot read {d / 'nope'}: No such file or directory\n"
            assert run_main([str(bad), str(d / "nope")])[:2] == (2, f"  {bad} (github-pat)\n")
            assert run_main(["--refilter", "zzz", str(clean)])[:2] == (0, str(clean) + "\n")
            sub = d / "g"
            sub.mkdir()
            subprocess.run(["git", "init", "-q", str(sub)], check=True)
            pinned = sub / "pin.txt"
            pinned.write_text(f"t = {GHP}\n")
            sha = hashlib.sha256(pinned.read_bytes()).hexdigest()
            (d / "secret-scan-allow.txt").write_text(f"# comment {sha} pin.txt\n\n{sha} pin.txt\n")
            assert run_main([str(pinned)]) == (0, "", "")  # pinned by exact path and hash
            other = sub / "other" / "pin.txt"
            other.parent.mkdir()
            other.write_text(pinned.read_text())
            assert run_main([str(other)])[0] == 1  # same basename, different path
            pinned.write_text(pinned.read_text() + "\n")
            assert run_main([str(pinned)])[0] == 1  # content changed since the pin
            ss.GL = (ss.GL[0], ss.GL[1], 3)
            assert run_main([str(clean)]) == (2, "", "secret_scan: 3 gitleaks regexes failed to compile\n")
        finally:
            ss.R, ss.GL = old_r, old_gl


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
