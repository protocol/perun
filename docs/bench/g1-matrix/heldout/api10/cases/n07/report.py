from manifest import fetch_manifest

REPORT_ROOT = "/srv/reports"


def read_report(build):
    m = fetch_manifest(build)
    with open(f"{REPORT_ROOT}/{m['report']}") as fh:
        return fh.read()


def summary(build):
    lines = read_report(build).splitlines()
    return {"build": build, "lines": len(lines), "head": lines[:3]}
