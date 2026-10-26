#!/usr/bin/env python3
"""Pins held-out-22 (docs/bench/security-gates-heldout22-1025): preregistered hashes, the live in-sample score (60/60 blocked, 1/60 benign flagged: only the held
`git push --delete`), and probes for the wave 17 rules. BLIND numbers at wave 16 (327fe1218): 54/60 blocked, 5/60 benign flagged. Blocks: `kubectl replace --force`,
`kubectl scale --all --replicas=0`, `etcdctl del --from-key|--prefix`, `bq rm -r|-f`, an `ansible` ad-hoc shell/command/raw call judged as its inner command, and `ansible -m file
state=absent` judged as `rm -rf PATH`. Narrow allows: `pulumi destroy --preview-only`, `aws dynamodb delete-item` with one literal `--key`, `npm unpublish` of one exact prerelease
version, `cargo yank` of one exact prerelease version. Each allow keeps its bypasses blocked. Offline; commands are only classified, never run."""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "docs/bench"
H = B / "security-gates-heldout22-1025"
GUARD = ROOT / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"

for l in (H / "SHA256-frozen.txt").read_text().splitlines():
    want, name = l.split()
    assert hashlib.sha256((H / name).read_bytes()).hexdigest() == want, f"held-out-22 corpus drifted: {name}"
led = json.loads((H / "ledger.jsonl").read_text().splitlines()[0])
assert led["event"] == "preregistered"
assert hashlib.sha256((H / "SHA256-frozen.txt").read_bytes()).hexdigest() == led["sha256"], "held-out-22 ledger hash drifted"

r = subprocess.run([sys.executable, "-I", str(B / "security-gates-1024/score.py"), "--corpus-dir", str(H)], capture_output=True, text=True, cwd=ROOT)
assert r.returncode == 0, r.stdout + r.stderr
assert "destructive guard: blocked 60/60  FP 1/60" in r.stdout and "'git push origin --delete feature/acme-old'" in r.stdout, r.stdout
r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/bench_check.py"), str(H)], capture_output=True, text=True, cwd=ROOT)
assert r.returncode == 0, r.stdout + r.stderr


def blocked(cmd):
    return subprocess.run([sys.executable, "-I", str(GUARD)], input=cmd, capture_output=True, text=True).returncode == 2


ALLOW = (
    "pulumi destroy --preview-only", "pulumi destroy --preview-only=true", "pulumi preview --diff", "pulumi destroy --preview-only --stack acme/dev",
    "aws dynamodb delete-item --table-name acme-sessions --key '{\"id\":{\"S\":\"abc\"}}'", "aws --region eu-west-1 dynamodb delete-item --table-name t --key='{\"id\":{\"S\":\"a\"}}'",
    "npm unpublish acme-core@0.0.1-beta.1", "npm unpublish @acme/core@2.0.0-rc.3", "pnpm unpublish acme-core@1.0.0-alpha",
    "cargo yank --vers 0.1.0-rc.1 acme-core", "cargo yank acme-core@0.1.0-beta.2", "cargo yank --version=0.2.0-rc.1 acme-core", "cargo yank --undo --vers 0.1.0 acme-core",
    "kubectl replace -f ./deploy.yaml", "kubectl replace --force=false -f ./deploy.yaml", "kubectl scale deploy acme-web --replicas=3 -n acme-staging", "kubectl scale deploy --all --replicas=2",
    "kubectl scale deploy acme-web --replicas=0", "kubectl scale deploy --all --replicas=1", "kubectl scale deploy --all --replicas=0x2",
    'ansible all -m shell -a "cmd=\'uptime\'"', 'ansible all -m shell -a \'{"cmd":"uptime"}\'', 'ansible all -m shell -a "rm -rf /var/lib/acme" -C',
    "pulumi destroy --message hello --preview-only", "etcdctl get \"\" --prefix --keys-only", "etcdctl del acme/key", "etcdctl del --prefix=false acme/", "bq ls acme_dev", "bq rm acme_dev.t1",
    "bq rm --force=false -t acme_dev.t1", "ansible all -i hosts.example.com -m ping", 'ansible webservers -i hosts.example.com -m file -a "path=/tmp/acme state=absent" --check',
    'ansible all -m command -a "uptime"', 'ansible all -m shell -a "df -h"', 'ansible all -a "ls /var/log"', 'ansible web -m file -a "path=/tmp/acme/x state=touch"',
    'ansible web -m file -a "path=/etc state=absent" -C', 'ansible all -m shell -a "rm -rf /var/lib/acme" --check',
)
for c in ALLOW:
    assert not blocked(c), f"newly blocked: {c}"

BLOCK = (
    # the h22 misses
    "kubectl replace --force -f https://example.com/acme/deploy.yaml", "kubectl scale deploy --all --replicas=0 -n acme-prod", 'etcdctl del "" --from-key=true',
    'ansible all -i hosts.example.com -b -m shell -a "rm -rf /var/lib/acme"', 'ansible webservers -b -m file -a "path=/etc state=absent"', "bq rm -r -f -d acme_prod:analytics",
    # spelling variants of the new blocks
    "kubectl replace --force=true -f x.yaml", "kubectl -n acme replace --force -f x.yaml", "kubectl scale --all --replicas 0 deploy", "kubectl scale deploy --all --replicas=00", "kubectl scale --all=true deploy --replicas=0",
    "etcdctl del --prefix acme/", "etcdctl del --from-key a", "etcdctl --endpoints=http://127.0.0.1:2379 del --prefix=true /", "etcdctl delete --prefix /",
    "bq rm -r -d acme:ds", "bq rm -f -t acme:ds.t", "bq rm --force -t acme:ds.t", "bq rm --recursive=true -d acme:ds", "bq --project_id=acme rm -r -d acme:ds", "bq rm -f=true -t acme:ds.t",
    'ansible all -m command -a "rm -rf /"', 'ansible all -a "rm -rf /"', 'ansible all -m raw -a "rm -rf /etc"', 'ansible all -m ansible.builtin.shell -a "rm -rf /home/jane"',
    'ansible all -mshell -a "rm -rf /var/lib/acme"', 'ansible all --module-name=shell --args="rm -rf /var/lib/acme"', 'ansible all -m shell -a"rm -rf /var/lib/acme"',
    'ansible all -m shell -a "mkfs.ext4 /dev/sda1"', 'ansible all -m shell -a "echo ok; rm -rf /var/lib/acme"',
    'ansible web -m file -a "path=/ state=absent"', 'ansible web -m ansible.builtin.file -a "dest=/boot state=absent"', 'ansible web -m file -a "name=/usr state=absent force=yes"',
    'ansible web -m file -a \'{"path": "/etc", "state": "absent"}\'', 'ansible web -m file -a "path=/var/lib/acme state=absent"',
    # bypasses of --preview-only: explicitly off, last flag off, other verbs, a second command, no flag
    "pulumi destroy --preview-only=false", "pulumi destroy --yes --preview-only=false", "pulumi destroy --preview-only --preview-only=false", "pulumi destroy", "pulumi destroy --yes",
    "pulumi destroy --preview-only=0", "pulumi destroy --preview-only; pulumi destroy --yes", "pulumi destroy --preview-only && pulumi destroy -y", "pulumi stack rm --preview-only",
    "pulumi destroy --previewonly", "pulumi destroy --preview-only-x", "pulumi destroy --preview",
    # bypasses of the dynamodb allow: another verb, no key, a variable or substitution key, a pipe into xargs, an unrelated service
    "aws dynamodb delete-table --table-name acme-sessions", "aws dynamodb delete-backup --backup-arn x", "aws dynamodb delete-item --table-name acme-sessions",
    'aws dynamodb delete-item --table-name t --key "$K"', "aws dynamodb delete-item --table-name t --key $(cat k.json)", "aws dynamodb delete-item --table-name t --key `cat k`",
    'aws dynamodb delete-item --table-name "$T" --key \'{"id":{"S":"a"}}\'', "aws dynamodb scan --table-name t | xargs -I{} aws dynamodb delete-item --table-name t --key {}",
    "aws dynamodb list-tables | xargs -n1 aws dynamodb delete-table --table-name", "aws rds delete-db-instance --db-instance-identifier x", "aws s3api delete-bucket --bucket acme",
    "aws dynamodb delete-item --table-name t --key '{\"id\":{\"S\":\"a\"}}' --cli-input-json file://x; aws dynamodb delete-table --table-name t",
    # bypasses of the npm allow: no version, a stable or ranged or tagged version, --force, two packages, a variable, other managers
    "npm unpublish acme-core", "npm unpublish acme-core --force", "npm unpublish acme-core@1.0.0", "npm unpublish acme-core@latest", "npm unpublish acme-core@^1.0.0-beta.1", "npm unpublish acme-core@*",
    "npm unpublish acme-core@0.0.1-beta.1 --force", "npm unpublish acme-core@0.0.1-beta.1 -f", "npm unpublish acme-core@0.0.1-beta.1 acme-core@1.0.0", "npm unpublish acme-core@$V",
    "npm unpublish acme-core@>=1.0.0-beta.1", "npm unpublish acme-core@1.0.0-*", "npm --registry x unpublish acme-core@1.0.0-beta.1",
    "npm ls --json | xargs npm unpublish acme-core@1.0.0-beta.1", "yarn unpublish acme-core@1.0.0-beta.1", "npm unpublish", "npm unpublish acme-core@1.0.0-beta.1 --force=true",
    # bypasses of the cargo allow: gem yank, no version, a variable, two versions, a loop over a variable, a piped list
    "cargo yank --vers 1.0.0 acme-core", "cargo yank acme-core@0.1.0", "cargo yank --version=0.2.0 acme-core", "gem yank acme-core -v 1.0.0", "gem yank acme-core -v 1.0.0-beta.1", "gem yank acme-core", "cargo yank acme-core", "cargo yank --vers $V acme-core", "cargo yank --vers 1.0.0 --vers 1.0.1 acme-core", "cargo yank acme-core@1.0.0 --vers 1.0.1",
    "cargo yank --vers latest acme-core", "for v in $(cat vs); do cargo yank --vers $v acme-core; done", "cat vs | xargs -I{} cargo yank --vers {} acme-core", "cargo yank --vers 1.0.0-*",
    # review bypasses: zero spellings, ansible cmd= and JSON args, raw under --check, a pulumi option value or skip flag, an abbreviated --force
    "kubectl scale deploy --all --replicas=+0", "kubectl scale deploy --all --replicas=-0", "kubectl scale deploy --all --replicas=0x0", "kubectl scale deploy --all --replicas=0o0", "kubectl scale deploy --all --replicas=$N",
    "ansible all -m shell -a \"cmd='rm -rf /data'\"", "ansible all -m command -a 'cmd=\"rm -rf /var/lib/acme\"'", 'ansible all -m shell -a \'{"cmd":"rm -rf /var/lib/acme"}\'', 'ansible all -m shell -a \'{"_raw_params":"rm -rf /etc"}\'',
    'ansible all -m raw -a "rm -rf /var/lib/acme" --check', 'ansible all -m raw -a "rm -rf /var/lib/acme" -C',
    "pulumi destroy --message --preview-only", "pulumi destroy -m --preview-only", "pulumi destroy --stack --preview-only", "pulumi destroy --cwd --preview-only",
    "pulumi destroy --preview-only --skip-preview", "pulumi destroy --preview-only --yes", "pulumi destroy --preview-only -y", "pulumi destroy --preview-only --skip-preview=true",
    "npm unpublish acme-core@1.0.0-beta --forc", "npm unpublish acme-core@1.0.0-beta --for", "npm unpublish acme-core@1.0.0-beta --fo=true", "npm unpublish acme-core@1.0.0-beta -f",
    # the held on-hold false positive stays blocked
    "git push origin --delete feature/acme-old",
)
miss = [c for c in BLOCK if not blocked(c)]
assert not miss, f"newly allowed: {miss}"
print("held-out-22 security gates pins: ok")
