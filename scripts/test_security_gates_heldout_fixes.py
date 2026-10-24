#!/usr/bin/env python3
"""Regression for the gate rules added after docs/bench/security-gates-heldout-1024 (provider-format secret patterns, cloud/orchestration/store destructive rules).

Each rule has variants whose values differ from the held-out corpus, plus decoys that must stay allowed. Secret
values are fake and assembled from fragments so this file never trips the privacy gate. Commands are only classified.
"""
import importlib.util, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dg", ROOT / ".claude/skills/agentic-delivery/scripts/destructive_guard.py")
dg = importlib.util.module_from_spec(spec); spec.loader.exec_module(dg)
H, M = "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "Qw3Er5Ty7Ui9Op1As2Df4Gh6Jk8Lz0Xc"
B64 = "Zm9vYmFyYmF6cXV4cXV1eHF1dXV4"
LEAK = {
    "aws_secret_env": 'AWS_SECRET_ACCESS_KEY="' + M + H[:8] + '"',
    "aws_secret_colon": "aws_secret_access_key: " + M + H[:8],
    "twilio_sid": "A" "C" + H,
    "twilio_token_json": '{"authToken": "' + H + '"}',
    "twilio_token_env": "AUTH_TOKEN=" + H,
    "jwt": "eyJ" "hbGciOiJIUzI1NiJ9.eyJ" + "zdWIiOiJ4eHh4eHh4In0." + M[:20],
    "azure_account": "AccountKey=" + M * 2 + "==",
    "azure_sas": "SharedAccessKey=" + M * 2 + "=",
    "discord": "N" + M[:24] + "." + "Xy12Za." + M[:27],
    "linear": "lin_" "api_" + M + H[:8],
    "linear_oauth": "lin_" "oauth_" + M + H[:8],
    "mailgun": "key" "-" + H,
    "dockerhub": "dckr" "_pat_" + M[:27],
    "telegram": "bot1234567890:" "AA" + M + "x",
    "telegram_bare": "token 987654321:" "AA" + M + "x end",
}
OK = {
    "aws_doc_secret": "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiC" "YEXAMPLEKEY",
    "aws_secret_ref": "aws_secret_access_key = ${AWS_SECRET}",
    "aws_secret_short": "aws_secret_access_key = abc123",
    "twilio_token_short": "auth_token = " + H[:20],
    "sha1_commit": "commit " + H + H[:8],
    "jwt_header_only": 'header {"alg":"HS256"} eyJ' "hbGciOiJIUzI1NiJ9 decoded",
    "monkey_key": "monkey" "-" + H,
    "discord_dotted": "Module.Section.SubSectionNameThatIsLongEnoughToLookLike",
    "linear_short": "lin_" "api_ prefix is documented",
    "telegram_doc": "https://api.telegram.org/bot<TOKEN>/sendMessage",
    "ratio": "ts 20260301:AAB-12",
}
BAD = [
    "aws s3 rm s3://b --recursive", "aws s3 rm --recursive s3://b/p/", "aws --profile p s3 rb s3://b --force", "sudo aws s3 rb --force s3://b",
    "aws ec2 terminate-instances --instance-ids i-1", "aws rds delete-db-cluster --db-cluster-identifier c",
    "aws rds delete-db-instance --db-instance-identifier d", "gcloud projects delete p", "gcloud --quiet projects delete p",
    "az group delete -n g -y", "terraform destroy", "terraform -chdir=infra destroy -auto-approve", "tofu destroy",
    "terraform apply -destroy", "terraform apply -auto-approve -destroy", "kubectl delete namespace prod", "kubectl delete ns prod",
    "kubectl -n x delete namespace/prod", "kubectl delete all --all", "kubectl delete all --all -n x", "kubectl delete all -A --all",
    "redis-cli FLUSHALL", "redis-cli -h h flushdb", 'mongo --eval "db.dropDatabase()"', "mongosh --eval 'db.dropDatabase()'",
    "wipefs -a /dev/sdb", "wipefs --all /dev/sdb", "diskutil eraseDisk APFS X disk2", "diskutil eraseVolume HFS+ X /Volumes/x",
    "eval $(echo " + B64 + " | base64 -d)", 'eval "$(base64 -d <<< ' + B64 + ')"', "bash -c \"$(echo " + B64 + " | base64 --decode)\"",
    "echo " + B64 + " | base64 -d | sh", "sh `echo " + B64 + " | base64 -d`", "ssh h 'terraform destroy'",
]
GOOD = [
    "aws s3 rm s3://b/key.txt", "aws s3 ls s3://b --recursive", "aws s3 rb s3://b", "aws ec2 describe-instances",
    "aws rds describe-db-instances", "gcloud projects list", "az group list", "terraform plan", "terraform plan -destroy",
    "terraform apply", "terraform init", "kubectl delete pod x", "kubectl delete pod x -n dev", "kubectl get namespaces",
    "kubectl delete all -l app=x", "redis-cli GET k", "redis-cli -h h info", "mongosh --eval 'db.stats()'", "wipefs -n /dev/sdb",
    "diskutil list", "diskutil info disk2", "echo " + B64 + " | base64 -d > out.bin", 'eval "$(ssh-agent -s)"', "base64 -d in.b64 > out",
    "git commit -m 'explain terraform destroy'",
]
fail = [f"guard missed: {c}" for c in BAD if not dg.check(c)] + [f"guard false positive: {c}" for c in GOOD if dg.check(c)]
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t)
    (t / ".banlist.txt").write_text((ROOT / ".banlist.txt").read_text())

    def flagged(text):
        (t / "x.txt").write_text(text + "\n")
        return subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", str(t / ".banlist.txt"),
                               str(t / "x.txt")], capture_output=True).returncode != 0
    fail += [f"gate missed: {k}" for k, v in LEAK.items() if not flagged("v=" + v)]
    fail += [f"gate false positive: {k}" for k, v in OK.items() if flagged(v)]
    # only the exact frozen held-out corpus paths are exempt from the privacy scan (no glob); same-named files elsewhere are not
    leak = "aws_secret_access_key = " + M + H[:8]
    subprocess.run(["git", "-C", str(t), "init", "-q"], check=True)
    for d, name in (("security-gates-heldout-1024", "secret-leaks.txt"), ("security-gates-x", "secret-leaks.txt")):
        (t / "docs/bench" / d).mkdir(parents=True)
        (t / "docs/bench" / d / name).write_text(leak + "\n")
    r = subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", str(t / ".banlist.txt"), str(t / "docs")], capture_output=True, text=True)
    fail += [] if "security-gates-x/secret-leaks.txt" in r.stderr and "heldout-1024" not in r.stderr else ["corpus exemption: wrong files flagged: " + r.stderr]
print("\n".join(fail) or f"PASS  security gates held-out fixes ({len(BAD)}+{len(LEAK)} caught, {len(GOOD)}+{len(OK)} allowed)")
sys.exit(1 if fail else 0)
