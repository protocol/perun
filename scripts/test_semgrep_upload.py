#!/usr/bin/env python3
"""Tests for the bundled CWE-434 rules (templates/semgrep-taint/upload.yml): perun.js.upload-multer-no-filter, perun.js.upload-express-fileupload-mv,
perun.py.upload-save-unrestricted, perun.go.upload-filename-path, perun.rb.upload-original-filename. Every rule carries metadata cwe "CWE-434".
Each rule has positive cases and a clean twin (an extension allowlist or a fileFilter in the same function). Werkzeug secure_filename keeps the
extension, so the canonical Flask save(secure_filename(f.filename)) is a required finding.

Fixtures are annotated like semgrep's own tests: `// ruleid: <id>` (or `# ruleid: <id>`) marks the NEXT line as a required finding, `ok:` marks the
next line as one that must stay clean, and every unannotated line must stay clean too. A multi-statement pattern reports at its first statement,
so its annotation sits above that statement. All names are fictional. RULES=<dir> checks another copy of the rules. The live check needs semgrep:
it prints SKIP and exits 0 without it, unless REQUIRE_SEMGREP=1, which fails instead. The offline pins always run. Plain asserts."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
IDS = ["perun.js.upload-multer-no-filter", "perun.js.upload-express-fileupload-mv", "perun.py.upload-save-unrestricted",
       "perun.go.upload-filename-path", "perun.rb.upload-original-filename"]

JS = '''const multer = require("multer");
const path = require("path");
const express = require("express");
const app = express();

// ruleid: perun.js.upload-multer-no-filter
const open1 = multer({ dest: "uploads/" });
// ruleid: perun.js.upload-multer-no-filter
const open2 = multer({ storage: multer.diskStorage({ destination: "uploads/" }), limits: { fileSize: 1024 } });
// ruleid: perun.js.upload-multer-no-filter
const memUpload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 1024 } });
const okMemory = multer({ storage: multer.memoryStorage(), fileFilter: (req, file, cb) => cb(null, file.mimetype === "image/png") });
app.post("/mem", memUpload.single("f"), (req, res) => {
  require("fs").writeFile("/srv/uploads/" + req.file.originalname, req.file.buffer, () => res.end());
});
// ruleid: perun.js.upload-multer-no-filter
const open3 = multer();
const okFilter = multer({ dest: "uploads/", fileFilter: (req, file, cb) => cb(null, file.mimetype === "image/png") });
const okShorthand = (fileFilter) => multer({ dest: "uploads/", fileFilter });
const okVia = (opts) => multer({ dest: "uploads/", ...opts });

app.post("/a", (req, res) => {
  // ruleid: perun.js.upload-express-fileupload-mv
  req.files.avatar.mv("/srv/up/" + req.files.avatar.name, () => res.end());
});

app.post("/b", (req, res) => {
  // ruleid: perun.js.upload-express-fileupload-mv
  const doc = req.files.doc;
  doc.mv(path.join("/srv/up", doc.name), () => res.end());
});

app.post("/c", (req, res) => {
  const doc = req.files.doc;
  const ext = path.extname(doc.name).toLowerCase();
  if (![".pdf", ".png"].includes(ext)) return res.sendStatus(400);
  doc.mv("/srv/up/" + Date.now() + ext, () => res.end());
});

app.post("/d", (req, res) => {
  const doc = req.files.doc;
  doc.mv("/srv/up/fixed-name.bin", () => res.end());
});
'''

PY = '''import os
from pathlib import Path
from flask import request
from werkzeug.utils import secure_filename

UP = "/srv/up"
OK_EXT = {"png", "pdf"}


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in OK_EXT


def direct():
    # ruleid: perun.py.upload-save-unrestricted
    request.files["doc"].save(os.path.join(UP, request.files["doc"].filename))


def via_var():
    # ruleid: perun.py.upload-save-unrestricted
    f = request.files["doc"]
    f.save(os.path.join(UP, f.filename))


def via_get():
    # ruleid: perun.py.upload-save-unrestricted
    f = request.files.get("doc")
    f.save(UP + "/" + f.filename)


def via_name():
    # ruleid: perun.py.upload-save-unrestricted
    f = request.files["doc"]
    name = f.filename
    f.save(os.path.join(UP, name))


def secure_name_keeps_ext():
    # ruleid: perun.py.upload-save-unrestricted
    f = request.files["doc"]
    f.save(os.path.join(UP, secure_filename(f.filename)))


def secure_guard_keeps_ext():
    # ruleid: perun.py.upload-save-unrestricted
    f = request.files["doc"]
    if secure_filename(f.filename) != f.filename:
        return "bad", 400
    f.save(os.path.join(UP, f.filename))


def clean_allowlist():
    f = request.files["doc"]
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".png", ".pdf"):
        return "bad", 400
    f.save(os.path.join(UP, "upload" + ext))


def clean_endswith():
    f = request.files["doc"]
    if not f.filename.endswith(".png"):
        return "bad", 400
    f.save(os.path.join(UP, f.filename))


def clean_generated():
    f = request.files["doc"]
    f.save(os.path.join(UP, "fixed-name.bin"))


def clean_helper_exit():
    f = request.files["doc"]
    if not allowed_file(f.filename):
        return "bad", 400
    f.save(os.path.join(UP, secure_filename(f.filename)))


def clean_lower_endswith():
    f = request.files["doc"]
    if not f.filename.lower().endswith((".png", ".pdf")):
        return "bad", 400
    f.save(os.path.join(UP, secure_filename(f.filename)))


def clean_path_suffix():
    f = request.files["doc"]
    if Path(f.filename).suffix.lower() not in {".png", ".pdf"}:
        return "bad", 400
    f.save(os.path.join(UP, secure_filename(f.filename)))


def helper_no_exit():
    # ruleid: perun.py.upload-save-unrestricted
    f = request.files["doc"]
    if not allowed_file(f.filename):
        print("odd name")
    f.save(os.path.join(UP, f.filename))
'''

GO = '''package bench

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
)

func create(w http.ResponseWriter, r *http.Request) {
	file, header, err := r.FormFile("doc")
	if err != nil {
		return
	}
	defer file.Close()
	// ruleid: perun.go.upload-filename-path
	dst, _ := os.Create(filepath.Join("/srv/up", header.Filename))
	io.Copy(dst, file)
}

func joinOnly(w http.ResponseWriter, r *http.Request) {
	_, hdr, _ := r.FormFile("doc")
	// ruleid: perun.go.upload-filename-path
	p := filepath.Join("/srv/up", hdr.Filename)
	_ = p
}

func multipartForm(w http.ResponseWriter, r *http.Request) {
	r.ParseMultipartForm(1 << 20)
	// ruleid: perun.go.upload-filename-path
	os.Create("/srv/up/" + r.MultipartForm.File["doc"][0].Filename)
}

func cleanExt(w http.ResponseWriter, r *http.Request) {
	file, header, _ := r.FormFile("doc")
	defer file.Close()
	ext := filepath.Ext(header.Filename)
	if ext != ".png" && ext != ".pdf" {
		return
	}
	dst, _ := os.Create(filepath.Join("/srv/up", "upload"+ext))
	io.Copy(dst, file)
}

func cleanGenerated(w http.ResponseWriter, r *http.Request) {
	file, _, _ := r.FormFile("doc")
	defer file.Close()
	dst, _ := os.Create(filepath.Join("/srv/up", "fixed-name.bin"))
	io.Copy(dst, file)
}

func notAnUpload(w http.ResponseWriter, r *http.Request) {
	var cfg struct{ Filename string }
	os.Create(filepath.Join("/srv/up", cfg.Filename))
}
'''

RB = '''class UploadsController < ApplicationController
  def create
    upload = params[:doc]
    # ruleid: perun.rb.upload-original-filename
    File.write(File.join("/srv/up", upload.original_filename), upload.read)
  end

  def open_mode
    upload = params[:doc]
    name = upload.original_filename
    # ruleid: perun.rb.upload-original-filename
    File.open("/srv/up/#{name}", "wb") { |f| f.write(upload.read) }
  end

  def clean_ext
    upload = params[:doc]
    ext = File.extname(upload.original_filename).downcase
    return head(:bad_request) unless %w[.png .pdf].include?(ext)
    File.write("/srv/up/upload#{ext}", upload.read)
  end

  def clean_generated
    upload = params[:doc]
    File.write("/srv/up/fixed-name.bin", upload.read)
  end

  def read_only
    upload = params[:doc]
    File.open("/srv/up/#{upload.original_filename}", "rb") { |f| f.read }
  end
end
'''

# memoryStorage with limits only and no write or serve of the buffer in the file: the clean twin of the memoryStorage positive in app.js.
JS_MEM = '''const multer = require("multer");
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 1024 } });
app.post("/count", upload.single("f"), (req, res) => {
  res.json({ bytes: req.file.buffer.length });
});
'''

FILES = {"mem.js": JS_MEM, "app.js": JS, "app.py": PY, "app.go": GO, "app.rb": RB}


def annotated(body, kind):
    """Return {line number of the annotated NEXT line: id} for `// kind: id` or `# kind: id` comments."""
    return {i + 2: m.group(1) for i, l in enumerate(body.splitlines())
            if (m := re.match(rf"\s*(?://|#) {kind}: (\S+)$", l))}


want = {n: annotated(b, "ruleid") for n, b in FILES.items()}
assert [len(v) for v in want.values()] == [0, 6, 7, 3, 2], [len(v) for v in want.values()]

# Offline pins: every rule exists, is CWE-434, and keeps its clean-twin guards.
rule = open(os.path.join(RULES, "upload.yml")).read()
# +2: the taint rules perun.{js,py}.unrestricted-upload live here too and are tested by test_semgrep_wired_cwe.py
assert rule.count('cwe: "CWE-434"') == len(IDS) + 2 == rule.count("\n- id: perun."), "every rule needs CWE-434 metadata"
for i in IDS:
    assert f"- id: {i}" in rule, i
assert "<... secure_filename(...) ...>" not in rule, "secure_filename keeps the extension: it must not suppress CWE-434"
for s in ("fileFilter", "path.extname", "os.path.splitext", "filepath.Ext", "File.extname", "$H.Filename", "original_filename"):
    assert s in rule, s

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for n, b in FILES.items():
            open(os.path.join(d, n), "w").write(b)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--"] + list(FILES),
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {n: {} for n in FILES}
    for x in r["results"]:
        if not re.search(r"\.perun\.\w+\.upload-", x["check_id"]):
            continue  # another bundled rule firing on a fixture line is not this file's concern
        assert x["extra"]["metadata"]["cwe"] in ("CWE-434", ["CWE-434"]), x["extra"]["metadata"]
        got[x["path"]][x["start"]["line"]] = re.search(r"perun\.\w+\.upload-[\w-]+$", x["check_id"]).group(0)  # the id is prefixed by the rules path, which can itself start with perun.
    norm = got
    assert norm == want, ("got", norm, "want", want)
    print("semgrep-upload: live ok")
elif os.environ.get("REQUIRE_SEMGREP") == "1":
    sys.exit("FAIL: semgrep not installed but REQUIRE_SEMGREP=1, so the live check cannot be skipped")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-upload: ok")
