# Registers scripts/test_doctor_newest_release.py with CI (see the "Per-PR tests" step in ci.yml).
python3 scripts/test_doctor_newest_release.py
python3 scripts/test_doctor_newest_release_remotes.py
