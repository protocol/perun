# Bundled semgrep Go path-traversal taint rule: a request value reaching os.Open/ReadFile/ServeFile is flagged, filepath.Base and a literal path are not. Needs semgrep; offline pins always run.
python3 scripts/test_semgrep_go_pathtrav.py
