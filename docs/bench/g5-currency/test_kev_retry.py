#!/usr/bin/env python3
"""Self-test: the CISA KEV fetch retries 3x on IncompleteRead/OSError, then gives up (kev_expected -> None)."""
import http.client, run_and_score as R

def flaky(errs):
    calls = []
    def fake(url, data=None):
        calls.append(url)
        if len(calls) <= errs:
            raise http.client.IncompleteRead(b"x") if len(calls) % 2 else OSError("reset")
        return {"vulnerabilities": [{"cveID": "CVE-1"}]}
    return fake, calls

def test():
    real = R.http
    try:
        R.http, calls = flaky(2)
        assert R.kev_ids() == {"CVE-1"} and len(calls) == 3
        R.http, calls = flaky(3)
        try:
            R.kev_ids(); assert False, "should raise"
        except (http.client.IncompleteRead, OSError):
            assert len(calls) == 3
        R.http, calls = flaky(9)
        assert R.kev_expected({}) is None and len(calls) == 3
    finally:
        R.http = real

if __name__ == "__main__":
    test(); print("ok")
