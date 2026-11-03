#!/usr/bin/env python3
"""G10 set1: materialize 7 small IaC/CI/secrets fixture repos as git repos under TARGET.
Usage: build.py TARGET [--truth PATH]   (TARGET must not exist; --truth writes truth rows)
Secrets are generated at run time from fragments with a seeded RNG, so nothing secret-shaped is committed
here. Two secrets exist only in history (committed, then deleted). Line numbers are computed from the
written text. Truth row: {fixture, file, line, class, kind: positive|decoy, history}. For history rows the
file/line refer to the commit that introduced it (`history: true`)."""
import json, os, random, subprocess, sys

R = random.Random(1103)
AL, UP, HEX = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", "0123456789abcdef"
pick = lambda a, n: "".join(R.choice(a) for _ in range(n))
AWS = "AK" + "IA" + pick(UP, 16)
GHP = "gh" + "p_" + pick(AL, 36)
STRIPE = "sk" + "_live_" + pick(AL, 24)
AWS2 = "AK" + "IA" + pick(UP, 16)
AWS_SECRET = pick(AL + "/+", 40)
PEM = "\n".join(["-----BEGIN RSA PRIV" + "ATE KEY-----"] + [pick(AL + "+/", 64) for _ in range(6)] + ["-----END RSA PRIV" + "ATE KEY-----"]) + "\n"
SHA = pick(HEX, 40)
SHA256 = pick(HEX, 64)

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

# 1 actions
def actions():
    f = "actions"; init(f)
    p = ".github/workflows/ci.yml"
    t = put(f, p, f"""name: ci
on:
  pull_request:
    types: [opened, edited]
permissions: write-all
jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: announce title
        run: echo "PR is ${{{{ github.event.pull_request.title }}}}"
      - name: announce branch
        run: |
          echo "branch ${{{{ github.head_ref }}}}" >> notes.txt
      - name: announce title safely
        env:
          TITLE: ${{{{ github.event.pull_request.title }}}}
        run: echo "PR is $TITLE"
      - uses: acme-labs/label-bot@main
      - uses: example-org/deploy-action@v2
      - uses: acme-labs/release-bot@{SHA}
        with:
          token: ${{{{ secrets.RELEASE_TOKEN }}}}
""")
    mark("positive", "actions-script-injection", f, p, t, "event.pull_request.title }}\"")
    mark("positive", "actions-script-injection", f, p, t, "github.head_ref")
    mark("positive", "actions-unpinned-third-party", f, p, t, "label-bot@main")
    mark("positive", "actions-unpinned-third-party", f, p, t, "deploy-action@v2")
    mark("positive", "actions-excessive-permissions", f, p, t, "write-all")
    mark("decoy", "actions-script-injection", f, p, t, "echo \"PR is $TITLE\"")
    mark("decoy", "actions-unpinned-third-party", f, p, t, "release-bot@" + SHA)
    mark("decoy", "actions-unpinned-third-party", f, p, t, "actions/checkout@v4")
    p = ".github/workflows/target.yml"
    t = put(f, p, """name: target
on: pull_request_target
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: make test
""")
    mark("positive", "actions-pull-request-target-checkout", f, p, t, "head.sha")
    commit(f, "add workflows")

# 2 docker
def docker():
    f = "docker"; init(f)
    t = put(f, "api/Dockerfile", """FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
""")
    mark("positive", "dockerfile-root", f, "api/Dockerfile", t, "CMD [")
    t = put(f, "worker/Dockerfile", """FROM node:20-slim
WORKDIR /srv
COPY . .
RUN npm ci
USER root
CMD ["node", "worker.js"]
""")
    mark("positive", "dockerfile-root", f, "worker/Dockerfile", t, "USER root")
    t = put(f, "tools/Dockerfile", """FROM debian:12-slim
RUN useradd -r app
RUN curl -fsSL https://get.example.com/install.sh | sh
USER app
""")
    mark("positive", "dockerfile-curl-pipe-shell", f, "tools/Dockerfile", t, "curl -fsSL")
    t = put(f, "web/Dockerfile", """FROM golang:1.22 AS build
WORKDIR /src
COPY . .
RUN go build -o /out/web .

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/web /web
USER nonroot
ENTRYPOINT ["/web"]
""")
    mark("decoy", "dockerfile-root", f, "web/Dockerfile", t, "USER nonroot")
    commit(f, "add images")

# 3 terraform
def terraform():
    f = "terraform"; init(f)
    p = "main.tf"
    t = put(f, p, """resource "aws_s3_bucket" "assets" {
  bucket = "example-assets"
}

resource "aws_s3_bucket_acl" "assets" {
  bucket = aws_s3_bucket.assets.id
  acl    = "public-read"
}

resource "aws_s3_bucket" "private" {
  bucket = "example-private"
}

resource "aws_s3_bucket_public_access_block" "private" {
  bucket                  = aws_s3_bucket.private.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_security_group" "admin" {
  name = "admin"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "web" {
  name = "web"
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier          = "main"
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  publicly_accessible = true
}
""")
    mark("positive", "terraform-public-bucket", f, p, t, 'acl    = "public-read"')
    mark("decoy", "terraform-public-bucket", f, p, t, "restrict_public_buckets")
    mark("positive", "terraform-open-ssh", f, p, t, "from_port   = 22")
    mark("decoy", "terraform-open-ssh", f, p, t, "from_port   = 443")
    mark("positive", "terraform-public-database", f, p, t, "publicly_accessible = true")
    commit(f, "add infra")

# 4 k8s
def k8s():
    f = "k8s"; init(f)
    p = "pods.yaml"
    t = put(f, p, """apiVersion: v1
kind: Pod
metadata:
  name: debug
spec:
  hostNetwork: true
  containers:
    - name: shell
      image: registry.example.com/tools/shell:1.4
      securityContext:
        privileged: true
---
apiVersion: v1
kind: Pod
metadata:
  name: builder
spec:
  containers:
    - name: build
      image: registry.example.com/tools/build:2.0
      volumeMounts:
        - name: sock
          mountPath: /var/run/docker.sock
  volumes:
    - name: sock
      hostPath:
        path: /var/run/docker.sock
---
apiVersion: v1
kind: Pod
metadata:
  name: app
spec:
  containers:
    - name: app
      image: registry.example.com/app:3.1
      securityContext:
        privileged: false
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
""")
    mark("positive", "k8s-privileged-pod", f, p, t, "privileged: true")
    mark("positive", "k8s-host-network", f, p, t, "hostNetwork: true")
    mark("positive", "k8s-docker-socket", f, p, t, "path: /var/run/docker.sock")
    mark("decoy", "k8s-privileged-pod", f, p, t, "privileged: false")
    commit(f, "add pods")

# 5 secrets in tree
def secrets_tree():
    f = "secrets-tree"; init(f)
    t = put(f, ".env", f"AWS_ACCESS_KEY_ID={AWS}\nAWS_SECRET_ACCESS_KEY={AWS_SECRET}\nREGION=eu-west-1\n")
    mark("positive", "secret-in-tree", f, ".env", t, "AWS_ACCESS_KEY_ID")
    t = put(f, "app/client.py", f'import requests\n\nTOKEN = "{GHP}"\n\ndef repos():\n    return requests.get("https://api.example.com/repos", headers={{"Authorization": "token " + TOKEN}})\n')
    mark("positive", "secret-in-tree", f, "app/client.py", t, "TOKEN = ")
    t = put(f, "deploy/id_deploy", PEM)
    mark("positive", "secret-in-tree", f, "deploy/id_deploy", t, "-----BEGIN")
    t = put(f, ".env.example", "AWS_ACCESS_KEY_ID=changeme\nAWS_SECRET_ACCESS_KEY=changeme\nSTRIPE_KEY=${STRIPE_KEY}\n")
    mark("decoy", "secret-in-tree", f, ".env.example", t, "AWS_ACCESS_KEY_ID")
    t = put(f, "lock/pins.txt", f"vendored-lib 1.2.3 sha256:{SHA256}\nbuild-commit {SHA}\n")
    mark("decoy", "secret-in-tree", f, "lock/pins.txt", t, "sha256:")
    commit(f, "add app")

# 6 secrets in history only
def secrets_history():
    f = "secrets-history"; init(f)
    put(f, "README.md", "# svc\n")
    commit(f, "init")
    t = put(f, "config/prod.ini", f"[aws]\naccess_key = {AWS2}\nsecret = {pick(AL, 40)}\n")
    mark("positive", "secret-in-history-only", f, "config/prod.ini", t, "access_key", True)
    t = put(f, "billing.js", f'module.exports = {{ stripe: "{STRIPE}" }};\n')
    mark("positive", "secret-in-history-only", f, "billing.js", t, "stripe:", True)
    t = put(f, "build/manifest.txt", f"artifact-digest {SHA256}\n")
    mark("decoy", "secret-in-history-only", f, "build/manifest.txt", t, "artifact-digest", True)
    commit(f, "add config")
    for p in ("config/prod.ini", "billing.js", "build/manifest.txt"):
        os.remove(os.path.join(TARGET, f, p))
    put(f, "billing.js", 'module.exports = { stripe: process.env.STRIPE_KEY };\n')
    commit(f, "remove committed secrets, read from env")

# 7 clean control (no findings): hardened bundle, tests false-positive rate
def control():
    f = "control"; init(f)
    put(f, "Dockerfile", "FROM alpine:3.20\nRUN adduser -D app\nUSER app\nCMD [\"sleep\", \"1\"]\n")
    put(f, ".github/workflows/ci.yml", "name: ci\non: push\npermissions:\n  contents: read\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: make test\n")
    commit(f, "init")

if __name__ == "__main__":
    TARGET = os.path.abspath(sys.argv[1])
    for fn in (actions, docker, terraform, k8s, secrets_tree, secrets_history, control):
        os.makedirs(TARGET, exist_ok=True)
        fn()
    if "--truth" in sys.argv:
        json.dump(ROWS, open(sys.argv[sys.argv.index("--truth") + 1], "w"), indent=1)
        open(sys.argv[sys.argv.index("--truth") + 1], "a").write("\n")
    pos = sum(r["kind"] == "positive" for r in ROWS)
    print(pos, len(ROWS) - pos)
