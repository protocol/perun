#!/usr/bin/env python3
"""Wave-8 destructive_guard regressions (written against held-out-11 misses and false positives plus review leads): sgdisk zap/clear, truncation of
private keys and credential files (`> f`, `: > f`, `cat /dev/null > f`, `truncate`, `cp /dev/null`, `dd of=`), npm deprecate/owner rm, restic key remove and
unlock --remove-all, lvresize shrink, pvcreate -ff, zfs receive -F, zpool create -f, a padded command that must fail closed, plus the benign forms
that must stay allowed (`git clean -fdx ./sub`, `git stash drop stash@{N}`) and `git reset --hard HEAD`, which stays blocked. Offline; classified only."""
import importlib.util, pathlib, time

G = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", G)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

BAD = [
    "sgdisk --zap-all /dev/sdb", "sgdisk -Z /dev/sdb", "sgdisk -o /dev/sdb", "sgdisk --clear /dev/sdb", "sgdisk -og /dev/sdb", "sgdisk --zap /dev/sdb",
    "cat /dev/null > ~/.ssh/id_rsa", ": > ~/.ssh/id_ed25519", "> ~/.ssh/authorized_keys", "true > ./server.pem", "printf '' > $HOME/.aws/credentials", "echo -n > ./tls/site.key",
    ": > .env", "truncate -s0 ~/.ssh/id_rsa", "truncate -s 0 ./notes-key.pem", "truncate --size=0 ./.env.production", "truncate -s 0 credentials.json",
    "cp /dev/null ~/.ssh/id_rsa", "cp /dev/null ./deploy.key", "install /dev/zero ~/.aws/credentials", "dd if=/dev/null of=./id_ed25519", "mv /dev/null ~/.ssh/id_rsa",
    "npm owner rm jane acme-core", "npm owner remove jane acme-core", "npm deprecate acme-core \"gone\"", "npm deprecate acme-core@1 old && npm owner rm jane acme-core",
    "npm --registry https://registry.example.com deprecate acme-core gone", "pnpm owner rm jane acme-core", "npm unpublish acme-core --force",
    "restic key remove abc123 -r /srv/r", "restic -r /srv/r key rm abc123", "restic unlock --remove-all -r /srv/r", "restic -r r unlock --remove-all",
    "lvresize -L -2G /dev/vg0/acme", "lvresize -L-2G vg0/acme", "lvresize --size 5G vg0/acme", "lvresize -l -50%FREE vg0/acme", "lvresize -r -L 1G vg0/acme", "lvm lvresize -L 1G vg0/acme", "lvreduce -L 1G vg0/acme",
    "pvcreate -ff /dev/sdb", "pvcreate -f -f /dev/sdb", "pvcreate --force --force /dev/sdb", "pvcreate -yff /dev/sdb", "lvm pvcreate -ff /dev/sdb",
    "zfs receive -F tank/acme", "zfs recv -F tank/acme", "zfs receive -uF tank/acme", "zfs send tank/a@s | zfs receive -F tank/b", "zpool create -f tank /dev/sdb", "zpool create -fo ashift=12 tank /dev/sdb",
    "git reset --hard HEAD", "git clean -fdx", "git clean -fdx .", "git clean -fd ./", "git clean -fdx ../x", "git clean -fdx /srv/acme", "git clean -fdx ./build/../..", "git clean -fdx :/",
    "git -C /srv/acme clean -fdx ./build", "cd /srv/acme && git clean -fdx ./build", "git clean -fdx $D", "git clean -fdx ./b*", "git stash drop", "git stash clear",
    "git stash drop stash@{0} stash@{1}", "git stash drop HEAD", "git stash drop $S",
    "git clean -fdx -e foo", "git clean -fdx --exclude foo", "git clean -fdx --exclude=foo", "git clean -fdx -e=foo", "git clean -fdxe foo", "GIT_WORK_TREE=/ git clean -fdx ./sub",
    "env GIT_DIR=/ git clean -fdx ./sub", "git clean -fdx ./.git", "git clean -fdx ./sub/.git",
    ": > ~/.git-credentials", "truncate -s 0 ./service-account-prod.json", ": > ~/.docker/config.json", "truncate -s0 ~/.config/gcloud/credentials.db", ": > .envrc", ": > .netrc",
    "tee ./deploy.key </dev/null", "cat /dev/null | tee ./deploy.key", ": | tee .env", "printf %s > ./site.pem", "tee ~/.ssh/id_rsa < /dev/null",
    "sgdisk -d 1 /dev/sdb", "sgdisk --delete=1 /dev/sdb", "sgdisk -n 1:0:0 /dev/sdb", "sgdisk --new=1:0:0 /dev/sdb", "sgdisk --load-backup=/tmp/b.bin /dev/sdb", "sgdisk --mbrtogpt /dev/sdb", "sgdisk -g /dev/sdb",
    "pvcreate -f /dev/sdb", "pvcreate --force /dev/sdb", "vgcreate -f vg0 /dev/sdb", "vgcreate -ff vg0 /dev/sdb", "vgcreate --force vg0 /dev/sdb",
    "npm deprecate acme-core gone \"\"", "npm deprecate acme-core@1 \"x\" \"\"",
    "bash -c '" + "x=1;" * 6000 + "z=rm; $z -rf /srv/acme'", "bash -c '" + "x=1;" * 6000 + "z=rm; echo $z'", "bash -c 'a=-rf; " + "#" * 21000 + "\nrm $a /srv/acme'",
]
GOOD = [
    "sgdisk -p /dev/sdb", "sgdisk --print /dev/sdb", "sgdisk --backup=/tmp/acme/t.bin /dev/sdb", "sgdisk --help",
    ": > ./out.log", "cat /dev/null > ./build.log", "true > ./flag", "echo hi > ~/.ssh/config", "echo x > ./id_notes.txt", "printf '' > ./empty.txt", "cat key.pem > ./copy.txt",
    ": > ./.env.example", "truncate -s 0 ./app.log", "truncate -s 0 ./run.txt", "cp /dev/null ./app.log", "cp ~/.ssh/id_rsa.bak ./id.copy", "dd if=/dev/zero of=./img bs=1 count=1",
    "npm deprecate acme-core \"\"", "npm owner ls acme-core", "npm owner add jane acme-core", "npm deprecate --help", "npm cache clean --force", "npm unpublish --help",
    "restic key list -r r", "restic unlock -r r", "restic snapshots -r r", "restic key remove --help",
    "lvresize -L +2G vg0/acme", "lvresize --size=+1G vg0/acme", "lvresize --test -L 1G vg0/acme", "lvextend -L +1G vg0/acme", "lvresize --help", "pvcreate /dev/sdb", "vgcreate vg0 /dev/sdb", "lvm pvs",
    "zfs receive tank/acme", "zfs receive -n -F tank/acme", "zfs list", "zpool create tank /dev/sdb", "zpool create -n tank /dev/sdb", "zpool status",
    "git clean -fdx ./build", "git clean -fd build", "git clean -fdx ./a/b ./c", "git clean -fdx -- ./build", "git clean -n -fd", "git clean --dry-run -fdx", "git stash drop stash@{0}", "git stash drop stash@{12}",
    "git clean -fdx -e foo ./build", "git clean -fdx --exclude=foo ./build", "GIT_PAGER=cat git log", "tee ./out.log </dev/null", "echo hi | tee ./.env.example", "cat /dev/null | tee ./out.log", "sgdisk -p -v /dev/sdb",
    "git stash list", "git stash", "git stash pop", "git status",
    "bash -c '" + "echo $x;" * 4000 + "ls'", "bash -c 'x=1; echo $x'",
]
for c in BAD:
    assert dg.check(c), f"missed: {c[:80]}"
for c in GOOD:
    assert not dg.check(c), f"false positive: {c[:80]}"

ADV = ["bash -c '" + "a=$b;b=$a;" * 12000 + "x=1'", "git clean -fdx " + "./a " * 20000, "truncate -s 0 " + "./a.log " * 20000, "lvresize " + "-L +1G " * 20000, ": > ~/x;" * 20000,
       "pvcreate " + "-f " * 20000, "restic key " * 20000, "npm owner " * 20000, "sgdisk " + "-p " * 20000]
for c in ADV:
    t = time.perf_counter()
    dg.check(c)
    assert time.perf_counter() - t < 1.0, f"slow ({time.perf_counter() - t:.2f}s): {c[:30]}"
print("guard wave-8 regressions: ok")
