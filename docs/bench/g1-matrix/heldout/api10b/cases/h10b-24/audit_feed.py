import logging
import requests

log = logging.getLogger("feed")
FEED = "https://feed.acme-audit.example.com/v1/events"


def pull_events(since):
    r = requests.get(FEED, params={"since": since}, timeout=10)
    r.raise_for_status()
    return r.json()["events"]


def summarize(events):
    counts = {}
    for ev in events:
        kind = str(ev.get("kind", "unknown"))
        counts[kind] = counts.get(kind, 0) + 1
        log.info("event %s from %s", ev.get("id"), ev.get("source"))
    return counts


def report(since):
    summary = summarize(pull_events(since))
    return {"total": sum(summary.values()), "by_kind": summary}


if __name__ == "__main__":
    print(report("2026-01-01T00:00:00Z"))
