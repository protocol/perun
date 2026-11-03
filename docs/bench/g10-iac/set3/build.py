#!/usr/bin/env python3
"""G10 set3: materialize 7 small IaC/CI/secrets fixture repos as git repos under TARGET.
Usage: build.py TARGET [--truth PATH]   (TARGET must not exist; --truth writes truth rows)
Secrets are generated at run time from fragments with a seeded RNG, so nothing secret-shaped is committed
here. One secret exists only in history (committed, then deleted). Line numbers are computed from the
written text. Truth row: {fixture, file, line, class, kind: positive|decoy, history}. For history rows the
file/line refer to the commit that introduced it (`history: true`). Decoys and the control are clean in every
respect (pinned actions, least permissions, hardened pods/images, described and encrypted Terraform)."""
import json, os, random, re, subprocess, sys

R = random.Random(3319)
AL, UP, HEX = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", "0123456789abcdef"
pick = lambda a, n: "".join(R.choice(a) for _ in range(n))
SG = "S" + "G." + pick(AL, 22) + "." + pick(AL, 43)
NPM = "np" + "m_" + pick(AL, 36)
STRIPE = "sk_" + "live_" + pick(AL, 24)
INTEG = "sha512-" + pick(AL + "+/", 86) + "=="
CO, SN, DIG = pick(HEX, 40), pick(HEX, 40), pick(HEX, 64)

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

DECOYS = []  # (fixture, path) of decoy/control files, scanned for stray issues at the end

def wf(name, on, step, persist="false"):
    """Hardened one-job workflow: pinned checkout, explicit read-only permissions; callers deviate once."""
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
          persist-credentials: {persist}
{step}"""

def pod(name, spec_extra="", tail=""):
    """Fully hardened Pod in namespace workloads; callers deviate once via spec_extra or text edits."""
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {name}
  namespace: workloads
spec:
  automountServiceAccountToken: false
{spec_extra}  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.com/workloads/{name}@sha256:{DIG}
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
          drop: ["ALL"]
{tail}"""

def vol(src):
    """tail for pod(): one volume mounted at /data; src is the volume source line."""
    return f"      volumeMounts:\n        - name: data\n          mountPath: /data\n  volumes:\n    - name: data\n      {src}\n"

def dockerfile(base="python:3.12-slim", extra=""):
    """Hardened image (pinned base, non-root user, healthcheck); `extra` is the one seeded line."""
    return f"""FROM {base}
WORKDIR /srv
COPY . /srv
{extra}HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import sys; sys.exit(0)"]
USER 10001
CMD ["python", "serve.py"]
"""

def clean(fx, path, text):
    """Register a decoy/control file for the final stray-issue scan."""
    DECOYS.append((fx, path, text))
    return text

# 1 workflows
def workflows():
    f = "workflows"; init(f)
    W = ".github/workflows/"
    p = W + "build.yml"
    t = put(f, p, wf("build", "  push:\n    branches: [main]", "      - run: make build\n", persist="true"))
    mark("positive", "actions-persist-credentials", f, p, t, "persist-credentials: true")
    p = W + "legacy-cmd.yml"
    t = put(f, p, wf("legacy-cmd", "  push:\n    branches: [main]", "      - run: make package\n        env:\n          ACTIONS_ALLOW_UNSECURE_COMMANDS: true\n"))
    mark("positive", "actions-unsecure-commands", f, p, t, "ACTIONS_ALLOW_UNSECURE_COMMANDS")
    p = W + "nodejs.yml"
    t = put(f, p, wf("nodejs", "  push:\n    branches: [main]", "      - uses: actions/setup-node@v4\n"))
    mark("positive", "actions-unpinned-first-party", f, p, t, "setup-node@v4")
    p = W + "nodejs-pinned.yml"
    t = clean(f, p, put(f, p, wf("nodejs-pinned", "  push:\n    branches: [main]", f"      - uses: actions/setup-node@{SN}\n")))
    mark("decoy", "actions-unpinned-first-party", f, p, t, "setup-node@" + SN)
    p = W + "stamp.yml"
    t = clean(f, p, put(f, p, wf("stamp", "  issues:\n    types: [opened]", '      - name: stamp\n        run: echo "built ${{ github.sha }} in run ${{ github.run_id }}"\n')))
    mark("decoy", "actions-script-injection", f, p, t, "github.run_id")
    commit(f, "add workflows")

# 2 containers
def containers():
    f = "containers"; init(f)
    p = "gateway/Dockerfile"
    t = put(f, p, dockerfile(base="python:latest"))
    mark("positive", "dockerfile-latest-tag", f, p, t, "FROM python:latest")
    p = "indexer/Dockerfile"
    t = put(f, p, dockerfile(extra="ADD https://downloads.example.com/tool.tar.gz /opt/\n"))
    mark("positive", "dockerfile-add-remote-url", f, p, t, "ADD https://")
    p = "bastion/Dockerfile"
    t = put(f, p, dockerfile(extra="EXPOSE 22\n"))
    mark("positive", "dockerfile-expose-ssh", f, p, t, "EXPOSE 22")
    p = "packer/Dockerfile"
    t = clean(f, p, put(f, p, dockerfile(extra="ADD vendor.tar.gz /opt/\nEXPOSE 8443\n")))
    mark("decoy", "dockerfile-add-remote-url", f, p, t, "ADD vendor.tar.gz")
    commit(f, "add images")

# 3 infra (terraform, one resource per file)
def infra():
    f = "infra"; init(f)
    p = "lb_public.tf"
    t = put(f, p, """resource "aws_lb_listener" "public" {
  load_balancer_arn = "arn:aws:elasticloadbalancing:eu-west-1:111122223333:loadbalancer/app/edge/0123456789abcdef"
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = "arn:aws:elasticloadbalancing:eu-west-1:111122223333:targetgroup/edge/0123456789abcdef"
  }
}
""")
    mark("positive", "terraform-plaintext-listener", f, p, t, '"HTTP"')
    p = "lb_secure.tf"
    t = clean(f, p, put(f, p, """resource "aws_lb_listener" "secure" {
  load_balancer_arn = "arn:aws:elasticloadbalancing:eu-west-1:111122223333:loadbalancer/app/edge/0123456789abcdef"
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = "arn:aws:acm:eu-west-1:111122223333:certificate/00000000-0000-0000-0000-000000000000"
  default_action {
    type             = "forward"
    target_group_arn = "arn:aws:elasticloadbalancing:eu-west-1:111122223333:targetgroup/edge/0123456789abcdef"
  }
}
"""))
    mark("decoy", "terraform-plaintext-listener", f, p, t, '"HTTPS"')
    p = "kms_signing.tf"
    t = put(f, p, """resource "aws_kms_key" "signing" {
  description             = "Signing key"
  deletion_window_in_days = 30
  enable_key_rotation     = false
}
""")
    mark("positive", "terraform-kms-no-rotation", f, p, t, "enable_key_rotation")
    p = "kms_payload.tf"
    t = clean(f, p, put(f, p, """resource "aws_kms_key" "payload" {
  description             = "Payload encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
"""))
    mark("decoy", "terraform-kms-no-rotation", f, p, t, "enable_key_rotation")
    p = "fn_url.tf"
    t = put(f, p, """resource "aws_lambda_function_url" "hook" {
  function_name      = "hook-handler"
  authorization_type = "NONE"
}
""")
    mark("positive", "terraform-lambda-url-no-auth", f, p, t, "authorization_type")
    p = "imds_open.tf"
    t = put(f, p, """resource "aws_instance" "batch" {
  ami           = "ami-0123456789abcdef0"
  instance_type = "t3.micro"
  monitoring    = true
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "optional"
  }
  root_block_device {
    encrypted = true
  }
}
""")
    mark("positive", "terraform-imds-v1", f, p, t, "http_tokens")
    p = "imds_strict.tf"
    t = clean(f, p, put(f, p, """resource "aws_instance" "api" {
  ami           = "ami-0123456789abcdef0"
  instance_type = "t3.micro"
  monitoring    = true
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }
  root_block_device {
    encrypted = true
  }
}
"""))
    mark("decoy", "terraform-imds-v1", f, p, t, "http_tokens")
    p = "eks_open.tf"
    t = put(f, p, """resource "aws_eks_cluster" "main" {
  name     = "main"
  role_arn = "arn:aws:iam::111122223333:role/eks-main"
  vpc_config {
    subnet_ids              = ["subnet-0123456789abcdef0"]
    endpoint_public_access  = true
    public_access_cidrs     = ["0.0.0.0/0"]
  }
}
""")
    mark("positive", "terraform-eks-public-endpoint", f, p, t, "public_access_cidrs")
    p = "trail.tf"
    t = put(f, p, """resource "aws_cloudtrail" "audit" {
  name                          = "audit"
  s3_bucket_name                = "example-audit-logs"
  is_multi_region_trail         = true
  enable_log_file_validation    = false
}
""")
    mark("positive", "terraform-trail-no-validation", f, p, t, "enable_log_file_validation")
    commit(f, "add infra")

# 4 manifests (k8s, one object per file)
def manifests():
    f = "manifests"; init(f)
    p = "ipc.yaml"
    t = put(f, p, pod("ipc-agent", "  hostIPC: true\n"))
    mark("positive", "k8s-host-ipc", f, p, t, "hostIPC: true")
    p = "escalate.yaml"
    t = put(f, p, pod("escalator").replace("allowPrivilegeEscalation: false", "allowPrivilegeEscalation: true"))
    mark("positive", "k8s-privilege-escalation", f, p, t, "allowPrivilegeEscalation: true")
    p = "node-conf.yaml"
    t = put(f, p, pod("node-conf", tail=vol("hostPath:\n        path: /etc")))
    mark("positive", "k8s-hostpath-mount", f, p, t, "path: /etc")
    p = "scratch.yaml"
    t = clean(f, p, put(f, p, pod("scratch", tail=vol("emptyDir: {}"))))
    mark("decoy", "k8s-hostpath-mount", f, p, t, "emptyDir")
    p = "fresh.yaml"
    t = put(f, p, pod("fresh").replace(f"@sha256:{DIG}", ":latest"))
    mark("positive", "k8s-latest-tag", f, p, t, ":latest")
    p = "ops-role.yaml"
    t = put(f, p, """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ops-all
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["*"]
""")
    mark("positive", "k8s-rbac-wildcard", f, p, t, 'verbs: ["*"]')
    p = "viewer-role.yaml"
    t = clean(f, p, put(f, p, """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pod-viewer
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
"""))
    mark("decoy", "k8s-rbac-wildcard", f, p, t, 'verbs: ["get", "list"]')
    commit(f, "add manifests")

# 5 secrets in tree
def tokens_tree():
    f = "tokens-tree"; init(f)
    p = "app/mailer.py"
    t = put(f, p, f'import os\n\nSENDGRID_API_KEY = "{SG}"\nSENDER = os.environ.get("SENDER", "noreply@example.com")\n')
    mark("positive", "secret-in-tree", f, p, t, "SENDGRID_API_KEY")
    p = ".npmrc"
    t = put(f, p, f"registry=https://registry.npmjs.org/\n//registry.npmjs.org/:_authToken={NPM}\n")
    mark("positive", "secret-in-tree", f, p, t, "_authToken")
    p = "docs/setup.md"
    t = clean(f, p, put(f, p, "# Setup\n\nExport your own key before running:\n\n    STRIPE_SECRET_KEY=sk_test_your_key_here\n"))
    mark("decoy", "secret-in-tree", f, p, t, "STRIPE_SECRET_KEY")
    p = "web/package-lock.json"
    t = clean(f, p, put(f, p, f'{{\n  "name": "web",\n  "lockfileVersion": 3,\n  "packages": {{\n    "node_modules/left-pad": {{\n      "version": "1.3.0",\n      "integrity": "{INTEG}"\n    }}\n  }}\n}}\n'))
    mark("decoy", "secret-in-tree", f, p, t, "integrity")
    commit(f, "add app")

# 6 secret in history only
def tokens_history():
    f = "tokens-history"; init(f)
    put(f, "README.md", "# billing\n")
    commit(f, "init")
    p = "billing.env"
    t = put(f, p, f"CURRENCY=eur\nSTRIPE_SECRET_KEY={STRIPE}\n")
    mark("positive", "secret-in-history-only", f, p, t, "STRIPE_SECRET_KEY", True)
    commit(f, "add billing settings")
    os.remove(os.path.join(TARGET, f, p))
    put(f, "README.md", "# billing\n\nSettings come from the environment.\n")
    commit(f, "remove committed key, read from env")

# 7 clean control
def control():
    f = "control"; init(f)
    clean(f, "Dockerfile", put(f, "Dockerfile", dockerfile()))
    clean(f, ".github/workflows/ci.yml", put(f, ".github/workflows/ci.yml", wf("ci", "  push:\n    branches: [main]", "      - run: make test\n")))
    clean(f, "pod.yaml", put(f, "pod.yaml", pod("svc")))
    clean(f, "key.tf", put(f, "key.tf", """resource "aws_kms_key" "state" {
  description             = "State encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
"""))
    commit(f, "init")

def checks():
    """Self-checks: counts, decoy/control cleanliness, decoy separation from positives."""
    pos = [r for r in ROWS if r["kind"] == "positive"]
    dec = [r for r in ROWS if r["kind"] == "decoy"]
    assert (len(pos), len(dec)) == (20, 10), (len(pos), len(dec))
    assert sum(r["history"] for r in ROWS) == 1
    bad = re.compile(r':latest|runAsUser: 0|USER (0|root)|@v\d|@main|@master|0\.0\.0\.0/0|privileged: true|host(PID|IPC|Network)|chmod .*777|write-all|"\*"|sk_live|AKIA|SG\.[A-Za-z0-9]{20}|npm_[A-Za-z0-9]{30}')
    for fx, path, text in DECOYS:
        assert not bad.search(text), (fx, path)
    for d in dec:
        for r in pos:
            assert (d["fixture"], d["file"]) != (r["fixture"], r["file"]) or abs(d["line"] - r["line"]) >= 7, d
    # control has no rows and truth files exist
    assert not [r for r in ROWS if r["fixture"] == "control"]
    for r in ROWS:
        if not r["history"]:
            assert os.path.exists(os.path.join(TARGET, r["fixture"], r["file"])), r

if __name__ == "__main__":
    TARGET = os.path.abspath(sys.argv[1])
    for fn in (workflows, containers, infra, manifests, tokens_tree, tokens_history, control):
        os.makedirs(TARGET, exist_ok=True)
        fn()
    checks()
    if "--truth" in sys.argv:
        json.dump(ROWS, open(sys.argv[sys.argv.index("--truth") + 1], "w"), indent=1)
        open(sys.argv[sys.argv.index("--truth") + 1], "a").write("\n")
    pos = sum(r["kind"] == "positive" for r in ROWS)
    print(pos, len(ROWS) - pos)
