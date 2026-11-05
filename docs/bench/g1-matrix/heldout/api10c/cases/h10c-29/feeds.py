import httpx

client = httpx.Client(verify=False, timeout=10.0)


def pull_feed(name):
    r = client.get(f"https://feeds.example.com/v1/{name}.json")
    r.raise_for_status()
    return r.json()


def titles(name):
    feed = pull_feed(name)
    return [entry["title"] for entry in feed.get("entries", [])]


def merged(names):
    out = []
    for n in names:
        out.extend(titles(n))
    return sorted(set(out))
