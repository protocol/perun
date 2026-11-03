#!/usr/bin/env python3
"""G10 set2: materialize 7 small IaC/CI/secrets fixture repos as git repos under TARGET.
Usage: build.py TARGET [--truth PATH]   (TARGET must not exist; --truth writes truth rows)
Secrets are generated at run time from fragments with a seeded RNG, so nothing secret-shaped is committed
here. One secret exists only in history (committed, then deleted). Line numbers are computed from the
written text. Truth row: {fixture, file, line, class, kind: positive|decoy, history}. For history rows the
file/line refer to the commit that introduced it (`history: true`). Decoys and the control are clean in every
respect (pinned actions, least permissions, hardened pods/images, described and encrypted Terraform)."""
import json, os, random, subprocess, sys

R = random.Random(2207)
AL, UP, HEX = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", "0123456789abcdef"
pick = lambda a, n: "".join(R.choice(a) for _ in range(n))
AWS = "AK" + "IA" + pick(UP, 16)
AWS_SECRET = pick(AL + "/+", 40)
SLACK = "xo" + "xb-" + pick("0123456789", 11) + "-" + pick("0123456789", 12) + "-" + pick(AL, 24)
GHS = "gh" + "s_" + pick(AL, 36)
DBPW = pick(AL, 18) + "!7"
IMGPW = pick(AL, 22)
PUBKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + pick(AL, 43)
CO, VND, DIG = pick(HEX, 40), pick(HEX, 40), pick(HEX, 64)

ROWS, TARGET = [], None
ENV = {**os.environ, "GIT_AUTHOR_NAME": "Bench Author", "GIT_COMMITTER_NAME": "Bench Author",
       "GIT_AUTHOR_EMAIL": "bench@example.com",
       "GIT_COMMITTER_EMAIL": "bench@example.com",
       "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}

def git(fx, *a):
    subprocess.run(["git", "-C", os.path.join(TARGET, fx), "-c", "commit.gpgsign=false", *a], check=True, env=ENV, capture_output=True)

def put(fx, path, text):
    p = os.path.join(TARGET, fx, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)
    return text

def mark(kind, cls, fx, path, text, token, history=False):
    n = [i for i, l in enumerate(text.splitlines(), 1) if token in l]
    assert len(n) == 1, (fx, path, token, n)
    ROWS.append(dict(fixture=fx, file=path, line=n[0], **{"class": cls}, kind=kind, history=history))

def commit(fx, msg):
    git(fx, "add", "-A")
    git(fx, "commit", "-m", msg)

def init(fx):
    os.makedirs(os.path.join(TARGET, fx))
    git(fx, "init", "-q", "-b", "main")

def wf(name, on, step):
    """Hardened one-job workflow: pinned checkout, no persisted credentials, explicit read-only permissions."""
    return f"""name: {name}
on:
{on}
permissions:
  contents: read
jobs:
  run:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@{CO}
        with:
          persist-credentials: false
{step}"""

def pod(name, spec_extra="", uid="runAsUser: 10001", nonroot="true", caps='drop: ["ALL"]'):
    """Fully hardened Pod; arguments introduce at most one deviation."""
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {name}
  namespace: apps
spec:
  automountServiceAccountToken: false
{spec_extra}  securityContext:
    runAsNonRoot: {nonroot}
    {uid}
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.com/apps/{name}@sha256:{DIG}
      resources:
        requests:
          cpu: 100m
          memory: 128Mi
        limits:
          cpu: 500m
          memory: 256Mi
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          {caps}
"""

def dockerfile(extra="", user="USER 10001"):
    """Hardened image; `extra` is the one seeded line, user the final USER line."""
    return f"""FROM python:3.12-slim
WORKDIR /app
COPY . /app
{extra}HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import sys; sys.exit(0)"]
{user}
CMD ["python", "main.py"]
"""

# 1 pipelines
def pipelines():
    f = "pipelines"; init(f)
    W = ".github/workflows/"
    p = W + "triage.yml"
    t = put(f, p, wf("triage", "  issues:\n    types: [opened]", '      - name: log issue\n        run: echo "new issue ${{ github.event.issue.title }}"\n'))
    mark("positive", "actions-script-injection", f, p, t, "github.event.issue.title")
    p = W + "release.yml"
    t = put(f, p, wf("release", "  push:\n    branches: [main]", '      - name: save message\n        run: echo "${{ github.event.head_commit.message }}" > msg.txt\n'))
    mark("positive", "actions-script-injection", f, p, t, "head_commit.message")
    p = W + "scan.yml"
    t = put(f, p, wf("scan", "  push:\n    branches: [main]", "      - uses: vendor-labs/scan-action@v3\n"))
    mark("positive", "actions-unpinned-third-party", f, p, t, "scan-action@v3")
    p = W + "notify.yml"
    t = put(f, p, wf("notify", "  push:\n    branches: [main]", "      - uses: notify-hub/send@master\n"))
    mark("positive", "actions-unpinned-third-party", f, p, t, "notify-hub/send@master")
    p = W + "preview.yml"
    t = put(f, p, f"""name: preview
on:
  pull_request_target:
    types: [opened]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@{CO}
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
          persist-credentials: false
      - run: make preview
""")
    mark("positive", "actions-pr-target-checkout", f, p, t, "pull_request.head.sha")
    p = W + "labels.yml"
    t = put(f, p, wf("labels", "  issues:\n    types: [opened]", '      - name: log issue\n        env:\n          TITLE: ${{ github.event.issue.title }}\n        run: echo "new issue $TITLE"\n'))
    mark("decoy", "actions-script-injection", f, p, t, 'echo "new issue $TITLE"')
    p = W + "publish.yml"
    t = put(f, p, wf("publish", "  push:\n    tags: [\"v*\"]", f"      - uses: vendor-labs/publish-action@{VND}\n"))
    mark("decoy", "actions-unpinned-third-party", f, p, t, "publish-action@" + VND)
    commit(f, "add workflows")

# 2 images
def images():
    f = "images"; init(f)
    p = "api/Dockerfile"
    t = put(f, p, dockerfile(f"ENV DB_PASSWORD={IMGPW}\n"))
    mark("positive", "dockerfile-secret-env", f, p, t, "DB_PASSWORD")
    p = "batch/Dockerfile"
    t = put(f, p, dockerfile("RUN chmod -R 777 /app\n"))
    mark("positive", "dockerfile-world-writable", f, p, t, "chmod -R 777")
    p = "cron/Dockerfile"
    t = put(f, p, dockerfile(user="USER 0"))
    mark("positive", "dockerfile-root", f, p, t, "USER 0")
    p = "site/Dockerfile"
    t = put(f, p, dockerfile("ENV APP_ENV=production\nRUN chmod -R 750 /app\n"))
    mark("decoy", "dockerfile-world-writable", f, p, t, "chmod -R 750")
    commit(f, "add images")

# 3 cloud (terraform, one resource per file)
def cloud():
    f = "cloud"; init(f)
    p = "iam_ops.tf"
    t = put(f, p, """resource "aws_iam_policy" "ops_full" {
  name        = "ops-full"
  description = "Operations policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "*"
      Resource = "*"
    }]
  })
}
""")
    mark("positive", "terraform-iam-wildcard", f, p, t, 'Action   = "*"')
    p = "iam_reports.tf"
    t = put(f, p, """resource "aws_iam_policy" "reports_read" {
  name        = "reports-read"
  description = "Read-only access to the reports bucket"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "arn:aws:s3:::example-reports/*"
    }]
  })
}
""")
    mark("decoy", "terraform-iam-wildcard", f, p, t, '"s3:GetObject"')
    p = "rdp.tf"
    t = put(f, p, """resource "aws_vpc_security_group_ingress_rule" "rdp" {
  security_group_id = "sg-0123456789abcdef0"
  description       = "Remote desktop"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 3389
  to_port           = 3389
  ip_protocol       = "tcp"
}
""")
    mark("positive", "terraform-open-admin-port", f, p, t, "cidr_ipv4")
    p = "ssh_internal.tf"
    t = put(f, p, """resource "aws_vpc_security_group_ingress_rule" "ssh_internal" {
  security_group_id = "sg-0123456789abcdef0"
  description       = "Shell access from the internal network"
  cidr_ipv4         = "10.20.0.0/16"
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}
""")
    mark("decoy", "terraform-open-admin-port", f, p, t, "cidr_ipv4")
    p = "scratch_disk.tf"
    t = put(f, p, """resource "aws_ebs_volume" "scratch" {
  availability_zone = "eu-west-1a"
  size              = 50
  encrypted         = false
  tags = {
    Name = "scratch"
  }
}
""")
    mark("positive", "terraform-unencrypted-storage", f, p, t, "encrypted         = false")
    p = "data_disk.tf"
    t = put(f, p, """resource "aws_ebs_volume" "data" {
  availability_zone = "eu-west-1a"
  size              = 100
  encrypted         = true
  kms_key_id        = "arn:aws:kms:eu-west-1:111122223333:key/00000000-0000-0000-0000-000000000000"
  tags = {
    Name = "data"
  }
}
""")
    mark("decoy", "terraform-unencrypted-storage", f, p, t, "encrypted         = true")
    p = "downloads_policy.tf"
    t = put(f, p, """resource "aws_s3_bucket_policy" "downloads" {
  bucket = "example-downloads"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::example-downloads/*"
    }]
  })
}
""")
    mark("positive", "terraform-public-bucket-policy", f, p, t, 'Principal = "*"')
    p = "orders_db.tf"
    t = put(f, p, f"""resource "aws_db_instance" "orders" {{
  identifier              = "orders"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "orders_admin"
  password                = "{DBPW}"
  storage_encrypted       = true
  publicly_accessible     = false
  backup_retention_period = 7
  deletion_protection     = true
}}
""")
    mark("positive", "terraform-hardcoded-password", f, p, t, "password ")
    commit(f, "add infra")

# 4 cluster (k8s, one object per file)
def cluster():
    f = "cluster"; init(f)
    p = "pid-probe.yaml"
    t = put(f, p, pod("pid-probe", "  hostPID: true\n"))
    mark("positive", "k8s-host-pid", f, p, t, "hostPID: true")
    p = "legacy.yaml"
    t = put(f, p, pod("legacy", uid="runAsUser: 0", nonroot="false"))
    mark("positive", "k8s-run-as-root", f, p, t, "runAsUser: 0")
    p = "mounter.yaml"
    t = put(f, p, pod("mounter", caps='drop: ["ALL"]\n          add: ["SYS_ADMIN"]'))
    mark("positive", "k8s-cap-sys-admin", f, p, t, 'add: ["SYS_ADMIN"]')
    p = "ci-admin.yaml"
    t = put(f, p, """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ci-runner-admin
subjects:
  - kind: ServiceAccount
    name: ci-runner
    namespace: apps
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
""")
    mark("positive", "k8s-cluster-admin-binding", f, p, t, "name: cluster-admin")
    p = "worker.yaml"
    t = put(f, p, pod("worker", "  hostPID: false\n"))
    mark("decoy", "k8s-host-pid", f, p, t, "hostPID: false")
    p = "auditor-view.yaml"
    t = put(f, p, """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: auditor-view
subjects:
  - kind: ServiceAccount
    name: auditor
    namespace: apps
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: view
""")
    mark("decoy", "k8s-cluster-admin-binding", f, p, t, "name: view")
    put(f, "pod-reader-role.yaml", """apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: apps
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
""")
    p = "pod-reader-binding.yaml"
    t = put(f, p, """apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: apps
subjects:
  - kind: ServiceAccount
    name: dashboard
    namespace: apps
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: pod-reader
""")
    mark("decoy", "k8s-cluster-admin-binding", f, p, t, "name: pod-reader")
    commit(f, "add manifests")

# 5 secrets in tree
def keys_tree():
    f = "keys-tree"; init(f)
    p = "scripts/upload.sh"
    t = put(f, p, f"#!/bin/sh\nexport AWS_ACCESS_KEY_ID={AWS}\nexport AWS_SECRET_ACCESS_KEY={AWS_SECRET}\naws s3 cp report.csv s3://example-reports/\n")
    mark("positive", "secret-in-tree", f, p, t, "AWS_ACCESS_KEY_ID")
    p = "config/notify.yaml"
    t = put(f, p, f"channel: alerts\nbot_token: {SLACK}\n")
    mark("positive", "secret-in-tree", f, p, t, "bot_token")
    p = "deploy/authorized_keys.pub"
    t = put(f, p, f"{PUBKEY} deploy@example.com\n")
    mark("decoy", "secret-in-tree", f, p, t, "ssh-ed25519")
    commit(f, "add scripts")

# 6 secret in history only
def keys_history():
    f = "keys-history"; init(f)
    put(f, "README.md", "# jobs\n")
    commit(f, "init")
    p = "deploy.env"
    t = put(f, p, f"REGION=eu-west-1\nGH_TOKEN={GHS}\n")
    mark("positive", "secret-in-history-only", f, p, t, "GH_TOKEN", True)
    commit(f, "add deploy settings")
    os.remove(os.path.join(TARGET, f, p))
    put(f, "README.md", "# jobs\n\nDeploy settings come from the environment.\n")
    commit(f, "remove committed token, read from env")

# 7 clean control
def control():
    f = "control"; init(f)
    put(f, "Dockerfile", dockerfile())
    put(f, ".github/workflows/ci.yml", wf("ci", "  push:\n    branches: [main]", "      - run: make test\n"))
    put(f, "pod.yaml", pod("svc"))
    put(f, "disk.tf", """resource "aws_ebs_volume" "state" {
  availability_zone = "eu-west-1a"
  size              = 20
  encrypted         = true
  kms_key_id        = "arn:aws:kms:eu-west-1:111122223333:key/00000000-0000-0000-0000-000000000000"
  tags = {
    Name = "state"
  }
}
""")
    commit(f, "init")

if __name__ == "__main__":
    TARGET = os.path.abspath(sys.argv[1])
    for fn in (pipelines, images, cloud, cluster, keys_tree, keys_history, control):
        os.makedirs(TARGET, exist_ok=True)
        fn()
    if "--truth" in sys.argv:
        json.dump(ROWS, open(sys.argv[sys.argv.index("--truth") + 1], "w"), indent=1)
        open(sys.argv[sys.argv.index("--truth") + 1], "a").write("\n")
    pos = sum(r["kind"] == "positive" for r in ROWS)
    print(pos, len(ROWS) - pos)
