from b1 import add

add("pos","python","httpx",{"archive.py": r'''from pathlib import Path

from source import get_layout

ARCHIVE = Path("/var/acme/archive")


def store(tenant, blob):
    layout = get_layout(tenant)
    dest = ARCHIVE / layout["folder"] / "latest.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)  §T
    return dest


def purge_empty():
    for d in ARCHIVE.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
''', "source.py": r'''import httpx

CLIENT = httpx.Client(base_url="https://layouts.example.com", timeout=5.0)


def get_layout(tenant):
    r = CLIENT.get(f"/tenants/{tenant}/layout")
    r.raise_for_status()
    return r.json()
'''})

add("neg","javascript","fetch",{"thumb.js": r'''const { execFile } = require('child_process');

const CODEC = /^[a-z0-9]{2,8}$/;

async function fetchProfile(id) {
  const res = await fetch(`https://profiles.example.com/v1/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('profile lookup failed');
  return res.json();
}

async function makeThumb(id, input) {
  const profile = await fetchProfile(id);
  if (!CODEC.test(profile.codec)) {
    throw new Error('codec rejected');
  }
  return new Promise((resolve, reject) => {
    execFile('acme-thumb', ['--codec', profile.codec, input], (err, out) => {
      if (err) return reject(err);
      resolve(out);
    });
  });
}

module.exports = { makeThumb };
'''})

add("neg","python","requests",{"lookup.py": r'''import sqlite3

from rates import fetch_rate

DB = sqlite3.connect("pricing.db")


def apply_rate(region):
    rate = fetch_rate(region)
    DB.execute(f"UPDATE regions SET tax = {rate['tax_pct']} WHERE code = ?", (region,))
    DB.commit()
''', "rates.py": r'''import re

import requests

PCT = re.compile(r"\d{1,2}(\.\d{1,2})?")


def fetch_rate(region):
    resp = requests.get(f"https://rates.example.com/v1/{region}", timeout=6)
    resp.raise_for_status()
    body = resp.json()
    if not PCT.fullmatch(str(body["tax_pct"])):
        raise ValueError("tax_pct malformed")
    return body
'''})

add("pos","javascript","axios",{"billing.js": r'''const https = require('https');
const axios = require('axios');

const agent = new https.Agent({ rejectUnauthorized: false });  §T

const client = axios.create({
  baseURL: 'https://billing.example.com/v3',
  httpsAgent: agent,
  timeout: 7000,
});

async function getInvoice(id) {
  const res = await client.get(`/invoices/${encodeURIComponent(id)}`);
  return res.data;
}

async function totalFor(ids) {
  const all = await Promise.all(ids.map(getInvoice));
  return all.reduce((sum, inv) => sum + Number(inv.amount), 0);
}

module.exports = { getInvoice, totalFor };
'''})

add("neg","javascript","axios",{"billing.js": r'''const fs = require('fs');
const https = require('https');
const axios = require('axios');

const agent = new https.Agent({
  rejectUnauthorized: true,
  ca: fs.readFileSync('/etc/ssl/certs/acme-internal-ca.pem'),
});

const client = axios.create({
  baseURL: 'https://billing.example.com/v3',
  httpsAgent: agent,
  timeout: 7000,
});

async function getInvoice(id) {
  const res = await client.get(`/invoices/${encodeURIComponent(id)}`);
  return res.data;
}

async function totalFor(ids) {
  const all = await Promise.all(ids.map(getInvoice));
  return all.reduce((sum, inv) => sum + Number(inv.amount), 0);
}

module.exports = { getInvoice, totalFor };
'''})

add("pos","python","httpx",{"geo.py": r'''import sqlite3

import httpx

DB = sqlite3.connect("places.db")


def lookup(zip_code):
    r = httpx.get("https://geo.example.com/v1/zip", params={"q": zip_code}, timeout=5.0)
    r.raise_for_status()
    return r.json()


def remember(zip_code):
    place = lookup(zip_code)
    query = "INSERT INTO places (zip, city) VALUES (?, '{}')".format(place["city"])
    DB.execute(query, (zip_code,))  §T
    DB.commit()


def known_cities():
    return [row[0] for row in DB.execute("SELECT DISTINCT city FROM places")]
'''})

add("neg","javascript","fetch",{"orders.js": r'''const knex = require('knex')({ client: 'pg', connection: 'postgres://db.example.com/acme' });

async function fetchCustomer(id) {
  const res = await fetch(`https://crm.example.com/customers/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('crm lookup failed');
  return res.json();
}

async function tagOrders(customerId) {
  const customer = await fetchCustomer(customerId);
  const rows = await knex.raw(
    'UPDATE orders SET segment = ? WHERE customer_id = ? RETURNING id',
    [customer.segment, customerId]
  );
  return rows.rows.length;
}

async function pending() {
  return knex('orders').where({ status: 'pending' }).count('* as n');
}

module.exports = { tagOrders, pending };
'''})

add("pos","javascript","axios",{"proxy.js": r'''const axios = require('axios');
const { discover } = require('./discovery');

async function callService(name, body) {
  const svc = await discover(name);
  const res = await axios.post(svc.endpoint + '/invoke', body, { timeout: 5000 });  §T
  return res.data;
}

module.exports = { callService };
''', "discovery.js": r'''const axios = require('axios');

const registry = axios.create({ baseURL: 'https://registry.example.com/v1', timeout: 4000 });

async function discover(name) {
  const res = await registry.get(`/services/${encodeURIComponent(name)}`);
  return res.data;
}

module.exports = { discover };
'''})

add("neg","python","httpx",{"stash.py": r'''from pathlib import Path
from uuid import UUID

from meta import get_meta

STASH = Path("/var/acme/stash")


def write_blob(asset, blob):
    meta = get_meta(asset)
    ident = UUID(meta["blob_id"])
    dest = STASH / f"{ident}.bin"
    dest.write_bytes(blob)
    return dest


def read_blob(asset):
    meta = get_meta(asset)
    return (STASH / f"{UUID(meta['blob_id'])}.bin").read_bytes()
''', "meta.py": r'''import httpx


def get_meta(asset):
    r = httpx.get(f"https://assets.example.com/meta/{asset}", timeout=5.0)
    r.raise_for_status()
    return r.json()
'''})

add("pos","python","httpx",{"deploy.py": r'''import subprocess

import httpx


def fetch_release(name):
    r = httpx.get(f"https://releases.example.com/v1/{name}", timeout=8.0)
    r.raise_for_status()
    return r.json()


def install(name):
    release = fetch_release(name)
    script = f"cd /opt/acme && ./install.sh {release['version']}"
    result = subprocess.run(script, shell=True, capture_output=True, text=True)  §T
    return result.returncode


def install_all(names):
    return {n: install(n) for n in names}
'''})

add("neg","javascript","fetch",{"routes.js": r'''const { fetchConfig } = require('./config');

const UPSTREAMS = new Map([
  ['primary', 'https://primary.example.com/ingest'],
  ['backup', 'https://backup.example.com/ingest'],
]);

async function push(tenant, records) {
  const cfg = await fetchConfig(tenant);
  const url = UPSTREAMS.get(cfg.upstream);
  if (!url) {
    throw new Error('unknown upstream');
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(records),
  });
  return res.status;
}

module.exports = { push };
''', "config.js": r'''async function fetchConfig(tenant) {
  const res = await fetch(`https://config.example.com/tenants/${encodeURIComponent(tenant)}`);
  if (!res.ok) throw new Error('config unavailable');
  return res.json();
}

module.exports = { fetchConfig };
'''})

add("neg","python","requests",{"netcheck.py": r'''import subprocess

import requests


def fetch_target(name):
    resp = requests.get(f"https://targets.example.com/v1/{name}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def check_port(name):
    target = fetch_target(name)
    port = int(target["port"])
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    cmd = f"nc -z -w 2 probe.example.com {port}"
    return subprocess.run(cmd, shell=True).returncode == 0


def check_many(names):
    return {n: check_port(n) for n in names}
'''})

add("pos","python","httpx",{"feeds.py": r'''import httpx

client = httpx.Client(verify=False, timeout=10.0)  §T


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
'''})

add("pos","javascript","axios",{"export.js": r'''const fs = require('fs/promises');
const axios = require('axios');

const OUT_DIR = '/srv/acme/exports/';

async function getJob(id) {
  const res = await axios.get(`https://jobs.example.com/v1/jobs/${encodeURIComponent(id)}`, {
    timeout: 6000,
  });
  return res.data;
}

async function writeResult(id, text) {
  const job = await getJob(id);
  await fs.writeFile(OUT_DIR + job.output_name, text);  §T
  return job.output_name;
}

module.exports = { writeResult };
'''})
