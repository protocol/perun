#!/usr/bin/env python3
"""Pins for guard wave 20: every review-3 finding and the held-out-25 misses, as deny and allow rows, plus 100 KB adversarial inputs that must classify in under 2 s.
Offline; commands are only classified, never run."""
import pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = ROOT / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"


def blocked(cmd):
    return subprocess.run([sys.executable, "-I", str(GUARD)], input=cmd, capture_output=True, text=True).returncode == 2


cy = lambda q: f'cypher-shell -a neo4j://graph.example.com "{q}"'
DANGEROUS = (
    # cypher: window, string, comment, comma pattern and WHERE-always-true bypasses
    cy("MATCH (n) WITH n,'" + "x" * 400 + "' AS p DETACH DELETE n"),
    cy("MATCH (n)" + " " * 400 + "DETACH DELETE n"),
    cy("MATCH (n) WITH ';' AS s DETACH DELETE n"),
    cy("MATCH (n) // ;\nDETACH DELETE n"),
    cy("MATCH (a:K), (n) DETACH DELETE n"),
    cy("MATCH (n) WHERE n.x=1 OR TRUE DETACH DELETE n"),
    cy("MATCH (n) WHERE (true) DETACH DELETE n"),
    cy("MATCH (n) WHERE 1<2 DETACH DELETE n"),
    cy("MATCH (n) WHERE NOT false DETACH DELETE n"),
    cy("MATCH (n) WHERE n.x IS NULL OR n.x IS NOT NULL DETACH DELETE n"),
    cy("MATCH (n) WHERE n.a = n.a DETACH DELETE n"),
    cy("CALL { MATCH (n) DETACH DELETE n } IN TRANSACTIONS"),
    # package removal: bundles with value flags, last switch wins, rpm names
    'apt remove libc6 -tstable',
    'apt-get remove libc6 -tbookworm-backports',
    'apt remove libc6 -tsid',
    'apt remove libc6 --simulate --simulate=no',
    'apt remove libc6 --simulate --no-simulate',
    'apt-get remove libc6 -o APT::Get::Simulate=true -o APT::Get::Simulate=false',
    'dnf remove glibc --setopt=tsflags=test --setopt=tsflags=',
    'apk del -p /x -p / busybox',
    'pacman -Rns linux -r /mnt -r /',
    'apt-get remove libc6 -o RootDir=/mnt -o RootDir=/',
    'dnf remove libgcc', 'dnf remove zlib', 'dnf remove libselinux', 'dnf remove python3-libs', 'yum remove python3-dnf', 'dnf remove rpm-libs',
    'dnf remove libdnf', 'dnf remove libstdc++', 'dnf remove libxcrypt', 'dnf remove krb5-libs',
    # find over system subtrees
    'find /etc/sudoers.d -exec chown a {} +', 'find /etc/ssh -exec chown a {} +', 'find /usr/bin -exec chown a {} +', 'find /usr/lib -exec chown a {} +',
    'find /boot/grub -exec chown a {} +', 'find /etc/shadow -exec chmod 777 {} +', 'find /Library -exec chown a {} +', 'find /System -exec chown a {} +',
    'find /private -exec chown a {} +', 'find /root/x -exec chown a {} +', 'find /home/u -exec chown a {} +', 'find /Users/u -exec chown a {} +',
    # chmod revoke on system files and directories
    'chmod go-x /etc', 'chmod go-rwx /etc', 'chmod go-rwx /etc/passwd', 'chmod go-rwx /etc/group', 'chmod go-rwx /etc/ld.so.cache',
    'chmod go-rwx /etc/resolv.conf', 'chmod go-rwx /etc/nsswitch.conf', 'chmod go-x /var', 'chmod go-x /home',
    # root lock
    "echo 'root:!' | chpasswd -e", "echo 'root:x' | chpasswd", 'vipw', 'sudo vigr', 'usermod -pxx root',
    # kubectl kinds
    'kubectl delete namespaces.v1 acme', 'kubectl delete projects.project.openshift.io acme',
    # held-out 25
    'sudo userdel -r deploy', 'userdel -fr deploy', 'deluser --remove-home deploy',
    "sudo sed -i 's/^PermitRootLogin.*/PermitRootLogin no/;s/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl restart sshd",
    "sed -i.bak -e 's/^PermitRootLogin.*/PermitRootLogin no/' -e 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config.d/50-acme.conf",
    'sudo iptables -P INPUT DROP && sudo iptables -F', 'ip6tables --policy OUTPUT REJECT',
    'git push origin --delete tmp/acme-experiment', 'git push origin --delete scratch/acme-spike',  # kept false positive: remote branch deletes need a human
    # review 1: map literal / SET label, WHERE tautologies, subpath revokes, core names
    cy("MATCH (n) WITH {a:1} AS m DETACH DELETE n"), cy("MATCH (n) SET n:Foo DETACH DELETE n"),
    cy("MATCH (n) WHERE 'a'='a' DETACH DELETE n"), cy("MATCH (n) WHERE 1 IN [1] DETACH DELETE n"), cy("MATCH (n) WHERE id(n) >= 0 DETACH DELETE n"),
    cy("MATCH (n) WHERE size(n.name) >= 0 DETACH DELETE n"), cy("MATCH (n) WHERE coalesce(n.x,1)=1 DETACH DELETE n"),
    'find /usr/bin -exec chmod go-rwx {} +', 'find /var -exec chmod go-rwx {} +', 'find /etc/ssl/certs -exec chmod go-rwx {} +',
    'apt remove libstdc++6', 'apt-get remove libcrypt1', 'apt remove libuuid1',
    'ls' + '\n' * 3000, 'echo ' + 'a' * 70000, 'git push origin --delete main', 'git push origin --delete tmp/acme-experiment main', 'git push origin --delete tmp/acme-experiment --force',
    # comments: a `#` inside a word or a quote is not a comment
    'echo a#b; rm -rf /', 'echo "# x"; rm -rf /', 'echo hi # c\nrm -rf /', 'rm -rf / # tidy',
)
BENIGN = (
    cy("MATCH (n:Tmp) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 1000 ROWS"),
    cy("MATCH (n:Tmp) DETACH DELETE n"), cy("MATCH (n {k:1}) DETACH DELETE n"), cy("MATCH (n:Tmp) WITH {a:1} AS m DETACH DELETE n"),
    cy("MATCH (n) WHERE n.expired = true DETACH DELETE n"), cy("MATCH (n) WHERE n.tmp IS NOT NULL DETACH DELETE n"),
    'find /etc/ssh -exec chmod go-rwx {} +', 'find /home/jane -exec chmod go-rwx {} +', cy("MATCH (n) WHERE n.id = 5 DETACH DELETE n"), cy("MATCH (n) RETURN count(n)"),
    'apt remove libc6 -s', 'apt remove libc6 -ys', 'apt-get remove libc6 --simulate=no --simulate', 'apt-get remove libc6 -o APT::Get::Simulate=false -o APT::Get::Simulate=true',
    'dnf remove python3.9-pip', 'dnf remove python3.11-devel',
    'find /usr/local/bin -exec chown jane {} +', 'find /var/www -exec chown www-data {} +', 'find /home/jane/proj -exec chown jane {} +',
    'find /home -maxdepth 1 -type d -exec chmod go-rwx {} +', 'find /home -exec chmod o-rwx {} +',
    'chmod go-rwx /etc/shadow', 'chmod go-rwx /etc/ssh/sshd_config', 'chmod go-rwx /home/jane', 'chmod go-rwx /root', 'chmod o-rwx /home',
    "echo 'deploy:pw' | chpasswd", 'usermod -aG docker jane',
    'kubectl delete namespace.foo.io x',
    'userdel deploy', 'iptables -L', 'iptables -P FORWARD DROP',
    "sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
    'ls # rm -rf /', 'rm -rf ./build # not /', "echo hi # it's fine", 'echo $# items', 'echo "a # b" && ls',
)
miss = [c for c in DANGEROUS if not blocked(c)]
assert not miss, f"newly allowed: {miss}"
fp = [c for c in BENIGN if blocked(c)]
assert not fp, f"newly blocked: {fp}"
for adv in (cy("match (a)" + ", (a)" * 14000 + " :x delete"), cy("MATCH (n) " * 10000), cy("'" * 100000), cy("/*" * 50000), cy("where " * 20000 + "delete"), cy("\\'" * 50000),
            "apt remove libc6 " + "-o RootDir=/mnt " * 6000, "dnf remove " + "python3-libs " * 8000, "echo " + "a #" * 30000, "echo " + "' " * 50000, "find " + "/etc/x " * 14000 + "-exec chown a {} +"):
    t = time.time()
    blocked(adv)
    assert time.time() - t < 2.0, f"slow on {adv[:30]!r}: {time.time() - t:.2f}s"
print("guard wave 20 pins: ok")
