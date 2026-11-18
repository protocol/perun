# Bundled CWE-434 upload rules (JS multer/express-fileupload, Python save, Go FormFile, Ruby original_filename): each flags a missing extension check provable in one function, and its clean twin stays silent. Needs semgrep; offline pins always run.
python3 -I scripts/test_semgrep_upload.py
