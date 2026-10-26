#!/usr/bin/env python3
"""Pins for guard wave 21: every review-2 finding with its bypass variants, the data-heredoc size-cap exemption, the split sshd_config lockout and the stdin-TTY hang.
Offline; commands are only classified, never run."""
import os, pathlib, pty, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = ROOT / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"


def blocked(cmd):
    return subprocess.run([sys.executable, "-I", str(GUARD)], input=cmd, capture_output=True, text=True).returncode == 2


cy = lambda q: f'cypher-shell -a neo4j://graph.example.com "{q}"'
BIG = "line of data\n" * 2500
DANGEROUS = tuple(cy(q) for q in (
    "MATCH (n) WHERE n.a IS NULL OR NOT n.a IS NULL DETACH DELETE n",
    "MATCH (n) WHERE NOT n.a IS NULL OR n.a IS NULL DETACH DELETE n",
    "MATCH (n) WHERE n.a IS NULL OR NOT (n.a IS NULL) DETACH DELETE n",
    "MATCH (n) WHERE n.x IS NULL OR (n.x) IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE n.x IS NULL OR toString(n.x) IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE n.x IS NULL OR exists(n.x) DETACH DELETE n",
    "MATCH (n) WHERE NOT exists(n.x) OR n.x IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE all(x IN [] WHERE n.a=1) DETACH DELETE n",
    "MATCH (n) WHERE n.a=1 OR all(x IN [] WHERE n.b=1) DETACH DELETE n",
    "MATCH (n) WHERE any(x IN [1] WHERE true) DETACH DELETE n",
    "MATCH ((n)) DETACH DELETE n",
    "MATCH ( ( n ) ) DETACH DELETE n",
    "MATCH (n) WHERE id(n) >= 0 DETACH DELETE n",
    "MATCH (n) WHERE id(n) = id(n) DETACH DELETE n",
    "MATCH (n) WHERE id(n) IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE size(n.t) >= 0 DETACH DELETE n",
    "MATCH (n) WHERE coalesce(n.x, 0) IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE 1 IN [1] DETACH DELETE n",
    "MATCH (n) WHERE exists(n.x) DETACH DELETE n",  # kept FP: a held-out pin
)) + (
    "bash <<'EOF'\n" + BIG + "EOF",  # a heredoc fed to a shell still counts
    "python3 - <<'EOF'\n" + BIG + "EOF",
    "cat <<'EOF' | bash\n" + BIG + "EOF",
    "cat >f <<'EOF'\n" + BIG,  # unterminated
    "cat >f <<EOF\n$(rm -rf /)\n" + BIG + "EOF",  # unquoted body expands
    "echo hi\n" * 2500,
    "sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config && sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config; perl -pi -e 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sed --in-place s/PasswordAuthentication.*/no/ /etc/ssh/sshd_config\nsed -ni s/PermitRootLogin.*/no/ /etc/ssh/sshd_config",
    "find /etc -exec chmod go-rwx {} +",
    "find /etc/pam.d -exec chmod go-rwx {} +",
    "find /etc/ssl/certs -exec chmod go-rwx {} +",
)
SAFE = tuple(cy(q) for q in (
    "MATCH (n) WHERE id(n) = 5 DETACH DELETE n",
    "MATCH (n) WHERE id(n) IN [1,2] DETACH DELETE n",
    "MATCH (n) WHERE elementId(n) = $id DETACH DELETE n",
    "MATCH (n) WHERE n.a IS NULL OR n.b IS NOT NULL DETACH DELETE n",
    "MATCH (n:Tmp) DETACH DELETE n",
)) + (
    "cat > f.txt <<'EOF'\n" + BIG + "EOF",
    "cat <<'EOF' > f.txt\n" + BIG + "EOF",
    "tee -a notes.txt <<'EOF'\n" + BIG + "EOF",
    "git commit -F - <<'EOF'\n" + "subject\n\n" + BIG + "EOF",
    "cat > f.txt <<EOF\n" + "x" * 70000 + "\nEOF",
    "find /etc/myapp -exec chmod go-rwx {} +",
    "sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config",
)

DANGEROUS += tuple(cy(q) for q in (
    "MATCH (n) WHERE elementId(n) IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE elementId(n) = elementId(n) DETACH DELETE n",
    "MATCH (n) WHERE elementId(n) <> '' DETACH DELETE n",
    "MATCH (n) WHERE elementId(n) STARTS WITH '' DETACH DELETE n",
    "MATCH (n) WHERE id(n) <> -1 DETACH DELETE n",
    "MATCH (n) WHERE id(n) >= -1 DETACH DELETE n",
    "MATCH (n) WHERE id(n) < 99999999999 DETACH DELETE n",
    "MATCH (n) WHERE id(n) IN range(0,99999999999) DETACH DELETE n",
    "MATCH (n) WHERE toString(id(n)) IS NOT NULL DETACH DELETE n",
    "MATCH (n) WHERE NOT (n.k IS NULL AND n.k IS NOT NULL) DETACH DELETE n",
    "MATCH (n) WHERE (n.a IS NULL OR n.a IS NOT NULL) AND true DETACH DELETE n",
    "MATCH (n) WHERE id(n) IS NOT NULL AND true DETACH DELETE n",
)) + (
    "cat >f <<EOF\n$(rm -rf /)\nEOF",
    "cat >f <<EOF\n`rm -rf /`\nEOF",
    "cat >f <<EOF\n$\\\n(rm -rf /)\nEOF",
    "cat >f <<\"EOF\"x\nEOF" if False else "tee f <<EOF\nx $(git push --force origin main) y\nEOF",
    "sed -i s/PermitRootLogin/no/ /etc/ssh/sshd_*; sed -i s/PasswordAuthentication/no/ /etc/ssh/sshd_*",
    "sed -i s/PermitRootLogin.*/no/ /etc/ssh/sshd_config; sed -i s/KbdInteractiveAuthentication.*/no/ /etc/ssh/sshd_config",
    "sudo sed -i s/PermitRootLogin.*/no/ /etc/ssh/sshd_config && sudo perl -pi -e s/PasswordAuthentication.*/no/ /etc/ssh/sshd_config",
    "cat >f <<'EOF'\nx\nEOF\n" + "#" * 10_000_001,  # hard ceiling even for data heredocs
)
SAFE += tuple(cy(q) for q in (
    "MATCH (n) WHERE elementId(n) IN $ids DETACH DELETE n",
    "MATCH (n) WHERE elementId(n) = 'abc' DETACH DELETE n",
)) + (
    "cat >f <<'EOF'\n$(rm -rf /)\nEOF",  # quoted tag: inert
    'cat >f <<"EOF"\n`rm -rf /`\nEOF',
    "cat >f <<EOF\nhome is $(pwd) and $(date)\nEOF",
    "sed -i s/PermitRootLogin.*/yes/ /etc/ssh/sshd_config; sed -i s/PasswordAuthentication.*/yes/ /etc/ssh/sshd_config",
    "sed -i 's/PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config; sed -i 's/PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config",
    "echo 'x=\"sed -i PermitRootLogin no sshd_config\" ; sed -i PasswordAuthentication no sshd_config'",
    "git log --grep='sed -i PermitRootLogin no sshd_config'; git log --grep='sed -i PasswordAuthentication no sshd_config'",
    "sed -i s/PermitRootLogin.*/no/ /etc/ssh/sshd_config; sed -i s/PasswordAuthentication.*/no/ /etc/ssh/sshd_config_x",
)

# base5 allowed these; the allowlist blocks them again (functions, NOT, ranges, property-vs-property, null pairs); rewrite with `v.prop OP literal`
KEPT_FP = tuple(cy(q) for q in (
    "MATCH (n) WHERE id(n) >= 100 DETACH DELETE n",
    "MATCH (n) WHERE size(n.tags) = 0 DETACH DELETE n",
    "MATCH (n) WHERE length(n.name) > 3 DETACH DELETE n",
    "MATCH (n) WHERE coalesce(n.deleted,false) DETACH DELETE n",
    "MATCH (n) WHERE NOT exists((n)--()) DETACH DELETE n",
    "MATCH (n) WHERE n.tmp IS NOT NULL AND size(n.tmp) > 0 DETACH DELETE n",
    "MATCH (n) WHERE 1 IN n.ids DETACH DELETE n",
    "MATCH (n) WHERE 5 IN n.scores DETACH DELETE n",
    "MATCH (n) WHERE id(n) IS NOT NULL AND n.k=1 DETACH DELETE n",
    "MATCH (n) WHERE any(x IN [1,2] WHERE x = n.k) DETACH DELETE n",
    "MATCH (n) WHERE n.a IS NULL AND n.b=1 OR n.a IS NOT NULL AND n.b=2 DETACH DELETE n",
    "MATCH (n) WHERE n.k=1 AND toString(n.a) IS NOT NULL AND n.a IS NULL DETACH DELETE n",
    "MATCH (n) WHERE (n.a IS NULL OR n.a IS NOT NULL) AND n.b=1 DETACH DELETE n",
))
DANGEROUS += KEPT_FP
DANGEROUS += tuple(cy(q) for q in (
    "MATCH (n) WHERE NOT (n.k=1 AND 1=2) DETACH DELETE n",
    "MATCH (n) WHERE NOT (1=2 AND n.k=1) DETACH DELETE n",
    "MATCH (n) WHERE NOT (n.k=1 AND 1<>1) DETACH DELETE n",
    "MATCH (n) WHERE NOT (n.k=1 AND coalesce(n.k,0) >= 0) DETACH DELETE n",
    "MATCH (n) WHERE NOT (n.k IS NULL AND size(n.l) >= 0) DETACH DELETE n",
    "MATCH (n) WHERE id(n) < 99999999 DETACH DELETE n",
    "MATCH (n) WHERE id(n) <= 99999999 DETACH DELETE n",
    "MATCH (n) WHERE id(n) < 1000000 DETACH DELETE n",
    "MATCH (n) WHERE id(n) < $x DETACH DELETE n",
    "MATCH (n) WHERE id(n) <= 0 OR id(n) > 0 DETACH DELETE n",
    "MATCH (n) WHERE NOT n.k=1 OR n.k=1 DETACH DELETE n",
    "MATCH (n) WHERE n.k=1 AND 1=2 DETACH DELETE n",
    "MATCH (n) WHERE n.a = n.b DETACH DELETE n",
)) + tuple(
    "cat >f <<EOF\n" + b + "\nEOF" for b in (
        "$(:) " * 32 + "$(rm -rf /)",
        "`:` " * 32 + "`rm -rf /`",
        "$(echo ')' ; rm -rf /)",
        "$(echo \\) ; rm -rf /)",
        '$(echo "("; rm -rf /)',
        "$(case x in x) rm -rf / ;; esac)",
        "$(echo # )\nrm -rf /)",
        "$(echo `echo ')'`; rm -rf /)",
        "\\\\$(rm -rf /)",  # an even run of backslashes leaves the substitution live
    )
) + (
    "sed -i 's/PermitRootLogin yes/PermitRootLogin no/;s/x/y/' sshd_config; sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/;s/x/y/' sshd_config",
    "ex -sc '%s/PermitRootLogin yes/PermitRootLogin no/|x' sshd_config; ex -sc '%s/PasswordAuthentication yes/PasswordAuthentication no/|x' sshd_config",
    "perl -pi -e 's/PermitRootLogin yes/PermitRootLogin no/ || 1' sshd_config; perl -pi -e 's/PasswordAuthentication yes/PasswordAuthentication no/ || 1' sshd_config",
    "sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config.d/*.conf; sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config.d/*.conf",
)
SAFE += tuple(cy(q) for q in (
    "MATCH (n) WHERE id(n) = 5 AND n.k=1 DETACH DELETE n",
    "MATCH (n) WHERE n.k STARTS WITH 'tmp' AND n:Tmp DETACH DELETE n",
    "MATCH (n) WHERE (n)--() DETACH DELETE n",
)) + (
    "cat >f <<EOF\n\\$(rm -rf /)\nEOF",  # escaped: literal text
    "cat >f <<EOF\nhome $HOME $(date) `hostname` $((1+2)) ${x:-d} $(pwd)\nEOF",
)

DANGEROUS += tuple(cy(q) for q in (
    "MATCH (n) WHERE (n)-[*0..]-() DETACH DELETE n",
    "MATCH (n) WHERE (n)-[*0..]-(:X) DETACH DELETE n",
    "MATCH (n) WHERE (n)-[*0]-(n) DETACH DELETE n",
    "MATCH (n) WHERE n.a IS NULL OR (n)-[*0..]-() DETACH DELETE n",
    "MATCH (n) WHERE n.a IS NULL OR n.a = 1 OR n.a <> 1 DETACH DELETE n",
    "MATCH (n) WHERE n.a = 1 OR n.a <> 1 OR n.a IS NULL DETACH DELETE n",
    "MATCH (n) WHERE n.a IS NULL OR n.a < 0 OR n.a >= 0 DETACH DELETE n",
    "MATCH (n) WHERE n.a = 1 OR n.a <> 1 DETACH DELETE n",
    "MATCH (n) WHERE NOT n.a = 1 OR n.a = 1 DETACH DELETE n",
    "MATCH (n) WHERE NOT n:Foo OR n:Foo DETACH DELETE n",
    "MATCH (n) WHERE NOT n.a IS NULL DETACH DELETE n",
    "MATCH (n) WHERE n.k IN [1,2] OR n.k IS NULL DETACH DELETE n",
)) + (
    "if true; then sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config; fi",
    "{ sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config; }",
    "for f in x; do sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; done; for f in x; do sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config; done",
    "A=1 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; A=1 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config",
    "env A=1 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; sudo -n sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config",
    "sudo -u root sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; doas sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config",
    "xargs sed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; nohup sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' sshd_config",
    "gsed -i 's/PermitRootLogin.*/PermitRootLogin no/' sshd_config; awk -i inplace '{sub(/PasswordAuthentication.*/,\"PasswordAuthentication no\")}1' sshd_config",
    "sed -i 's/PermitRootLogin.*/PermitRootLogin\\tno/' sshd_config; sed -i 's/PasswordAuthentication.*/PasswordAuthentication\\sno/' sshd_config",
    "sed -i s/PermitRootLogin.*/no/ sshd_config; sed -i s/ChallengeResponseAuthentication.*/no/ sshd_config",
)
DANGEROUS += tuple("cat >f <<EOF\n" + b + "\nEOF" for b in (
    "$(echo # )\nrm -rf /)",
    "text\n$(date) `rm -rf /` more",
    "$(case x in x) rm -rf / ;; esac)",
    "`echo $(rm -rf /)`",
))
SAFE += tuple(cy(q) for q in (
    "MATCH (n) WHERE n.a STARTS  WITH 'x' DETACH DELETE n",
    "MATCH (n) WHERE n.a STARTS\nWITH 'x' DETACH DELETE n",
    "MATCH (n) WHERE n.a STARTS /**/ WITH 'x' DETACH DELETE n",
    "MATCH (n) WHERE n.a = 1e3 DETACH DELETE n",
    "MATCH (n) WHERE n.a = 'it''s' DETACH DELETE n",
    "MATCH (n) WHERE n.a.b = 1 DETACH DELETE n",
    "MATCH (n) WHERE n.a = $p.name DETACH DELETE n",
)) + (
    "sed -i 's/PermitEmptyPasswords yes/PermitEmptyPasswords no/' /etc/ssh/sshd_config",
    "sed -i 's/ChrootDirectory.*/ChrootDirectory none/;s/PasswordAuthentication yes/no/' /etc/ssh/sshd_config",
    "cat >README.md <<EOF\n" + "use `x` here\n" * 17 + "EOF",
    "cat >f <<EOF\n" + "$(date)\n" * 40 + "EOF",
)

# review 4: shrunk grammar (any NOT, XOR, same-operand OR blocked), heredoc vetted to end of body, sshd any-token
DANGEROUS += tuple(cy(q) for q in (
    'MATCH (n) WHERE (n)--() OR NOT (n)--() DETACH DELETE n',
    'MATCH (n) WHERE (n)-->() OR NOT (n)-->() DETACH DELETE n',
    'MATCH (n) WHERE (n)-[]-() OR NOT (n)-[]-() DETACH DELETE n',
    'MATCH (n) WHERE (n)--() XOR NOT (n)--() DETACH DELETE n',
    'MATCH (n) WHERE NOT id(n) = 1 OR NOT id(n) = 2 DETACH DELETE n',
    'MATCH (n) WHERE NOT id(n) IN [1] OR NOT id(n) IN [2] DETACH DELETE n',
    'MATCH (n) WHERE id(n)=1 OR NOT id(n) = 1 DETACH DELETE n',
    'MATCH (n) WHERE n.a IN [1,2] OR NOT n.a IN [1, 2] DETACH DELETE n',
    'MATCH (n) WHERE n.a IN [1] OR NOT n.a IN[1] DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.a <> 1.0 DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.a <> 01 DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.a <> 1E0 DETACH DELETE n',
    'MATCH (n) WHERE n.a < 5 OR n.a > 3 DETACH DELETE n',
    'MATCH (n) WHERE n.a <= 5 OR n.a >= 5 DETACH DELETE n',
    'MATCH (n) WHERE n.a <> 1 OR n.a <> 2 DETACH DELETE n',
    'MATCH (n) WHERE NOT n.a = 1 OR NOT n.a = 2 DETACH DELETE n',
    'MATCH (n) WHERE n.a >= 1 OR n.a <= 1 DETACH DELETE n',
    'MATCH (n) WHERE n.a = true OR n.a <> TRUE DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.a < 1 OR n.a > 1 DETACH DELETE n',
    'MATCH (n) WHERE n.a = - 1 OR n.a <> -1 DETACH DELETE n',
    'MATCH (n) WHERE n.a = -1 OR n.a <> - 1 DETACH DELETE n',
    'MATCH (n) WHERE NOT (n)--() DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 AND NOT n.b = 2 DETACH DELETE n',
    'MATCH (n) WHERE NOT n:Foo DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.a = 2 DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.a = 2 OR n.a = 3 DETACH DELETE n',
)) + tuple((
    "sudo -p x sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sudo -p x sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sudo -D /tmp sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sudo -D /tmp sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sudo -r r sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sudo -r r sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sudo -t t sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sudo -t t sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sudo -u#0 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sudo -u#0 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "env -u FOO sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; env -u FOO sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "env -S x sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; env -S x sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "env -C / sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; env -C / sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "nice -n 5 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; nice -n 5 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "xargs -I {} sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; xargs -I {} sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "xargs -L 1 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; xargs -L 1 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "xargs -P 4 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; xargs -P 4 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "xargs -n1 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; xargs -n1 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "timeout 5 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; timeout 5 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "exec sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; exec sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "busybox sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; busybox sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "time -p sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; time -p sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "ionice -c3 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; ionice -c3 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "flock /x sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; flock /x sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "setsid sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; setsid sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "stdbuf -o0 sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; stdbuf -o0 sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "chroot / sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; chroot / sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "strace sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; strace sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "watch sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; watch sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "unshare sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; unshare sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "nsenter sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; nsenter sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "script -c sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; script -c sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "sudo --user root sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sudo --user root sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    "function f { sed -i 's/PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config; sed -i 's/PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config; }",
    "vim -es -c '%s/PermitRootLogin.*/PermitRootLogin no/|%s/PasswordAuthentication.*/PasswordAuthentication no/|x' /etc/ssh/sshd_config",
    'ed -s /etc/ssh/sshd_config <<EOF\n,s/PermitRootLogin.*/PermitRootLogin no/\n,s/PasswordAuthentication.*/PasswordAuthentication no/\nw\nEOF',
))
DANGEROUS += tuple("cat >f <<EOF\n" + b + "\nEOF" for b in (
    '`echo $(:)` `rm -rf /`',
    '$(echo "$(echo ")")"; rm -rf /)',
    '$(cat <<X\n)\nX\nrm -rf /)',
    '$(echo ${x:-)}; rm -rf /)',
    '$(date)\nrm -rf /',
    '$(git rev-parse HEAD)\nsudo reboot',
))
SAFE += tuple(cy(q) for q in (
    "MATCH (n) WHERE n.ts >= '2024' AND n.ts < '2025' DETACH DELETE n",
    "MATCH (n) WHERE n.ts > '2024' AND n.ts <= '2025' DETACH DELETE n",
    "MATCH (n) WHERE n.v >= 'a' AND n.v < 'b' AND n.w = 1 DETACH DELETE n",
    'MATCH (n) WHERE n.a = - 1 DETACH DELETE n',
    'MATCH (n) WHERE n.a = 1 OR n.b = 2 DETACH DELETE n',
    "MATCH (n) WHERE n.v = 'a' AND n.v <> 'b' DETACH DELETE n",
    "MATCH (n) WHERE n.a = 1 OR n.b IS NULL DETACH DELETE n",
))


def test_rows():
    miss = [c[:90] for c in DANGEROUS if not blocked(c)] + ["FP " + c[:90] for c in SAFE if blocked(c)]
    assert not miss, miss


def test_stdin_does_not_hang():
    r = subprocess.run([sys.executable, "-I", str(GUARD)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    assert r.returncode == 0
    try:
        m, s = pty.openpty()  # stdin is a terminal
    except OSError:
        return print("skip tty half: no pty in this sandbox")
    try:
        r = subprocess.run([sys.executable, "-I", str(GUARD)], stdin=s, capture_output=True, timeout=10)
        assert r.returncode == 0
    finally:
        os.close(m), os.close(s)


def test_wall_clock_cap():
    """stdin that never closes must end in a block after TIMEOUT seconds, not spin or wait forever."""
    p = subprocess.Popen([sys.executable, "-I", str(GUARD)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert p.wait(timeout=20) == 2 and b"did not finish" in p.stderr.read()
    finally:
        p.kill(), p.stdin.close(), p.stderr.close()


def test_regex_spin_is_killed():
    """A check spinning inside one C-level regex call (no bytecode boundary for a Python signal handler) still blocks."""
    spin = ("import importlib.util as u, re, sys; s = u.spec_from_file_location('g', sys.argv[1]); g = u.module_from_spec(s); "
            "s.loader.exec_module(g); g.TIMEOUT = 2; g.check = lambda c: re.match(r'(a+)+$', 'a' * 64 + 'b'); sys.exit(g.main())")
    r = subprocess.run([sys.executable, "-I", "-c", spin, str(GUARD)], input='{"tool_input":{"command":"ls"}}',
                       capture_output=True, text=True, timeout=20)
    assert r.returncode == 2 and "did not finish" in r.stderr, (r.returncode, r.stderr)


if __name__ == "__main__":
    test_rows(), test_stdin_does_not_hang(), test_wall_clock_cap(), test_regex_spin_is_killed()
    print("guard w21 ok")
