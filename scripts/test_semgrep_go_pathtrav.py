#!/usr/bin/env python3
"""Tests for the bundled semgrep rule perun.go.path-traversal (templates/semgrep-taint/go.yml): a net/http, gin or echo request value
reaching a path sink (open, read, write, create, remove, rename, stat, list, mkdir), directly or through filepath.Join. The only
sanitizer is a filepath.IsLocal confinement guard; filepath.Base alone is not one (Base("..") is ".."), and a literal path is never a finding.

Fixtures are annotated like semgrep's own tests: `// ruleid: <id>` marks the NEXT line as a required finding, `// ok: <id>` marks the next
line as one that must stay clean, and every unannotated line must stay clean too. The documented limits are pinned both ways: an allowlist-map
lookup and a Clean plus HasPrefix check still report (accepted noise, kept as ruleid), and a value read inside a helper is not followed (kept as todoruleid: a known miss, either outcome accepted).
All names and values are fictional. RULES=<dir> checks another copy of the rules. The live check needs semgrep: it prints SKIP and exits 0
without it, unless REQUIRE_SEMGREP=1 (the real-hub CI job sets it), which fails instead. The offline pins always run. Plain asserts."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
ID = "perun.go.path-traversal"

GO = '''package bench

import (
	"io/fs"
	"io/ioutil"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/labstack/echo/v4"
)

func query(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", r.URL.Query().Get("f")))
}

func queryIndex(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", r.URL.Query()["f"][0]))
}

func form(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.ReadFile("/srv/files/" + r.FormValue("f"))
}

func post(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	ioutil.ReadFile(r.PostFormValue("f"))
}

func pathValue(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", r.PathValue("name")))
}

func urlpath(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.OpenFile("/srv"+r.URL.Path, os.O_RDONLY, 0)
}

func serve(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	http.ServeFile(w, r, filepath.Join("/srv/files", r.URL.Query().Get("f")))
}

func viaVar(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("f")
	// ruleid: perun.go.path-traversal
	os.ReadFile(filepath.Join("/srv/files", name))
}

func create(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Create(filepath.Join("/srv/up", r.FormValue("f")))
}

func write(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.WriteFile(filepath.Join("/srv/up", r.FormValue("f")), []byte("x"), 0o600)
}

func remove(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Remove(filepath.Join("/srv/up", r.FormValue("f")))
}

func removeAll(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.RemoveAll(filepath.Join("/srv/up", r.FormValue("f")))
}

func rename(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Rename(filepath.Join("/srv/up", r.FormValue("f")), "/srv/old/a")
}

func renameTo(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Rename("/srv/up/a", filepath.Join("/srv/old", r.FormValue("f")))
}

func stat(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Stat(filepath.Join("/srv/files", r.FormValue("f")))
}

func readDir(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.ReadDir(filepath.Join("/srv/files", r.FormValue("d")))
}

func mkdir(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.MkdirAll(filepath.Join("/srv/up", r.FormValue("d")), 0o700)
}

func ginHandler(c *gin.Context) {
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", c.Query("f")))
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", c.Param("f")))
}

func ginClosure() gin.HandlerFunc {
	return func(c *gin.Context) {
		// ruleid: perun.go.path-traversal
		os.Open(filepath.Join("/srv/files", c.DefaultQuery("f", "a")))
	}
}

func echoHandler(c echo.Context) error {
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", c.QueryParam("f")))
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", c.Param("f")))
	return nil
}

func baseAlone(w http.ResponseWriter, r *http.Request) {
	// Base("..") is "..", so Base alone confines nothing.
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", filepath.Base(r.URL.Query().Get("f"))))
}

func pathBaseAlone(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.ReadFile("/srv/files/" + path.Base(r.FormValue("f")))
}

func localGuard(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("f")
	if !filepath.IsLocal(name) {
		return
	}
	// ok: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", name))
}

func localBranch(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("f")
	if filepath.IsLocal(name) {
		// ok: perun.go.path-traversal
		os.Open(filepath.Join("/srv/files", name))
	}
}

func localGuardWrite(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("name")
	if !filepath.IsLocal(name) {
		http.NotFound(w, r)
		return
	}
	// ok: perun.go.path-traversal
	os.WriteFile(filepath.Join("/srv/up", name), []byte("x"), 0o600)
}

func chmod(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Chmod(r.Form.Get("f"), 0o600)
	// ruleid: perun.go.path-traversal
	os.Chown(r.FormValue("f"), 1, 1)
	// ruleid: perun.go.path-traversal
	os.Truncate(r.FormValue("f"), 0)
}

func linkSink(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	os.Symlink(r.FormValue("f"), "/srv/l")
	// ruleid: perun.go.path-traversal
	os.Symlink("/srv/a", r.FormValue("f"))
	// ruleid: perun.go.path-traversal
	os.Link(r.FormValue("f"), "/srv/l")
	// ruleid: perun.go.path-traversal
	os.Link("/srv/a", r.FormValue("f"))
}

func walkRead(w http.ResponseWriter, r *http.Request) {
	// ruleid: perun.go.path-traversal
	filepath.WalkDir(r.FormValue("f"), nil)
	// ruleid: perun.go.path-traversal
	ioutil.ReadDir(r.FormValue("f"))
	// ruleid: perun.go.path-traversal
	fs.ReadFile(os.DirFS("/srv"), r.FormValue("f"))
}

func ginGet(c *gin.Context) {
	q, _ := c.GetQuery("f")
	// ruleid: perun.go.path-traversal
	os.Open(q)
}

func invertedGuard(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("f")
	if !filepath.IsLocal(name) {
		// ruleid: perun.go.path-traversal
		os.Open(name)
	}
}

func otherVarGuard(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("f")
	other := "a.txt"
	if !filepath.IsLocal(other) {
		return
	}
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", name))
}

func nestedReturnGuard(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("f")
	if !filepath.IsLocal(name) {
		if r.Method == "HEAD" {
			return
		}
	}
	// ruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", name))
}

func openRoot(w http.ResponseWriter, r *http.Request) {
	root, err := os.OpenRoot("/srv/files")
	if err != nil {
		return
	}
	// ok: perun.go.path-traversal
	root.Open(r.URL.Query().Get("f"))
}

func literal(w http.ResponseWriter, r *http.Request) {
	// ok: perun.go.path-traversal
	os.ReadFile("/srv/files/a.txt")
}

func notAPath(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("X-Name", r.URL.Query().Get("f"))
}

func allowlistMapLimit(w http.ResponseWriter, r *http.Request) {
	files := map[string]string{"a": "/srv/files/a.txt"}
	name := files[r.URL.Query().Get("f")]
	// Documented limit: a map lookup is not recognised as a sanitizer, so this safe code still reports.
	// ruleid: perun.go.path-traversal
	os.Open(name)
}

func cleanPrefixLimit(w http.ResponseWriter, r *http.Request) {
	p := filepath.Join("/srv/files", r.URL.Query().Get("f"))
	if !strings.HasPrefix(p, "/srv/files/") {
		return
	}
	// Documented limit: Clean plus HasPrefix confines the path but is not recognised, so this safe code still reports.
	// ruleid: perun.go.path-traversal
	os.Open(p)
}

func readName(r *http.Request) string { return r.URL.Query().Get("f") }

func helperLimit(w http.ResponseWriter, r *http.Request) {
	// Documented limit: the value is read in a helper function and is not followed (cross-function flow needs Semgrep Pro).
	// todoruleid: perun.go.path-traversal
	os.Open(filepath.Join("/srv/files", readName(r)))
}
'''


def annotated(body, kind):
    """Return {line number of the annotated NEXT line} for `// ruleid:`/`// ok:` comments naming ID."""
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*// {kind}: {re.escape(ID)}$", l)}


want, ok, todo = annotated(GO, "ruleid"), annotated(GO, "ok"), annotated(GO, "todoruleid")
assert len(want) == 40 and len(ok) == 5 and len(todo) == 1, (len(want), len(ok), len(todo))

# Offline pins: the rule keeps its sources, sinks and confinement sanitizers, and filepath.Base is never one.
rule = open(os.path.join(RULES, "go.yml")).read()
blk = rule[rule.index(f"- id: {ID}"):].split("\n- id: ")[0]
for s in ("mode: taint", "$R.URL.Query().Get(...)", "$R.URL.Query()[...]", "$R.FormValue(...)", "$R.PathValue(...)", "$C.Query(...)", "$C.Param(...)",
          "$C.QueryParam(...)", "*gin.Context", "echo.Context", "os.Open($S)", "os.ReadFile($S)", "ioutil.ReadFile($S)", "http.ServeFile($W, $R, $S)",
          "os.Create($S)", "os.WriteFile($S, ...)", "os.Remove($S)", "os.RemoveAll($S)", "os.Rename($S, ...)", "os.Rename($O, $S)", "os.Stat($S)",
          "os.ReadDir($S)", "os.MkdirAll($S, ...)", "filepath.IsLocal($P)", "$R.Form.Get(...)", "$C.GetQuery(...)", "os.Chmod($S, ...)", "os.Chown($S, ...)",
          "os.Truncate($S, ...)", "os.Symlink($O, $S)", "os.Link($O, $S)", "filepath.WalkDir($S, ...)", "ioutil.ReadDir($S)", "fs.ReadFile($FS, $S)",
          "does not follow symlinks"):
    assert s in blk, s
san = blk.split("pattern-sanitizers:")[1].split("pattern-sinks:")[0]
assert "Base" not in san, "filepath.Base must not sanitize"

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.go"), "w").write(GO)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.go"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(ID)}
    got -= todo  # todoruleid: a known miss, either outcome is accepted (a future detection must not fail the test)
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-go-pathtrav: live ok")
elif os.environ.get("REQUIRE_SEMGREP") == "1":
    sys.exit("FAIL: semgrep not installed but REQUIRE_SEMGREP=1, so the live check cannot be skipped")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-go-pathtrav: ok")
