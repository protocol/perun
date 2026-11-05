C = []
def add(kind, lang, fw, files):
    C.append((kind, lang, fw, files))

add("pos","python","requests",{"sync.py": r'''import sqlite3
import requests

DB = sqlite3.connect("shipments.db")
BASE = "https://carriers.example.com/v1"


def load_order(order_id):
    resp = requests.get(f"{BASE}/orders/{int(order_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def record_carrier(order_id):
    data = load_order(order_id)
    carrier = data["carrier_name"]
    DB.execute(f"INSERT INTO carriers (order_id, name) VALUES ({int(order_id)}, '{carrier}')")  §T
    DB.commit()


def count_for(order_id):
    cur = DB.execute("SELECT COUNT(*) FROM carriers WHERE order_id = ?", (int(order_id),))
    return cur.fetchone()[0]


if __name__ == "__main__":
    record_carrier(1042)
    print(count_for(1042))
'''})

add("neg","python","requests",{"sync.py": r'''import sqlite3
import requests

DB = sqlite3.connect("shipments.db")
BASE = "https://carriers.example.com/v1"


def load_order(order_id):
    resp = requests.get(f"{BASE}/orders/{int(order_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def record_carrier(order_id):
    data = load_order(order_id)
    carrier = data["carrier_name"]
    DB.execute(
        "INSERT INTO carriers (order_id, name) VALUES (?, ?)",
        (int(order_id), carrier),
    )
    DB.commit()


def count_for(order_id):
    cur = DB.execute("SELECT COUNT(*) FROM carriers WHERE order_id = ?", (int(order_id),))
    return cur.fetchone()[0]


if __name__ == "__main__":
    record_carrier(1042)
    print(count_for(1042))
'''})

add("neg","python","httpx",{"report.py": r'''import os
from pathlib import Path

import httpx

EXPORT_DIR = Path("/srv/acme/exports").resolve()


def fetch_manifest(job):
    r = httpx.get(f"https://reports.example.com/jobs/{job}", timeout=8.0)
    r.raise_for_status()
    return r.json()


def export_path(job):
    manifest = fetch_manifest(job)
    name = os.path.basename(manifest["filename"])
    target = (EXPORT_DIR / name).resolve()
    if EXPORT_DIR not in target.parents:
        raise ValueError("path outside export dir")
    return target


def save_export(job, payload):
    target = export_path(job)
    target.write_bytes(payload)
    return target


def list_exports():
    return sorted(p.name for p in EXPORT_DIR.iterdir())
'''})

add("pos","javascript","fetch",{"crawler.js": r'''const MAX_PAGES = 5;

async function getJson(url) {
  const res = await fetch(url, { headers: { accept: 'application/json' } });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

async function crawlCatalog() {
  const pages = [];
  let page = await getJson('https://catalog.example.com/v2/items');
  pages.push(page.items);
  for (let i = 1; i < MAX_PAGES && page.next_url; i += 1) {
    const follow = await fetch(page.next_url, { method: 'GET' });  §T
    page = await follow.json();
    pages.push(page.items);
  }
  return pages.flat();
}

async function countItems() {
  const items = await crawlCatalog();
  return items.length;
}

module.exports = { crawlCatalog, countItems };
'''})

add("pos","python","requests",{"gateway.py": r'''import subprocess

from client import fetch_job


def run_job(job_id):
    job = fetch_job(job_id)
    cmd = "backup-tool --target " + job["target_host"]
    subprocess.run(cmd, shell=True, check=True)  §T
    return job["target_host"]


def run_all(ids):
    return [run_job(i) for i in ids]
''', "client.py": r'''import requests

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def fetch_job(job_id):
    resp = SESSION.get(f"https://jobs.example.com/api/jobs/{int(job_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()
'''})

add("neg","python","httpx",{"router.py": r'''from urllib.parse import urlparse

import httpx

ALLOWED_HOSTS = {"hooks.example.com", "events.example.com"}


def fetch_subscription(sub_id):
    r = httpx.get(f"https://subs.example.com/v1/{sub_id}", timeout=5.0)
    r.raise_for_status()
    return r.json()


def deliver(sub_id, event):
    sub = fetch_subscription(sub_id)
    target = urlparse(sub["callback"])
    if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
        raise ValueError("callback host not permitted")
    return httpx.post(sub["callback"], json=event, timeout=5.0)


def deliver_many(sub_ids, event):
    return [deliver(s, event).status_code for s in sub_ids]
'''})

add("pos","javascript","axios",{"store.js": r'''const axios = require('axios');
const mysql = require('mysql2/promise');
const { getVendor } = require('./vendorClient');

async function saveVendor(id) {
  const conn = await mysql.createConnection({ host: 'db.example.com', user: 'acme' });
  const vendor = await getVendor(id);
  await conn.query(`UPDATE vendors SET label = '${vendor.display_name}' WHERE id = ?`, [id]);  §T
  await conn.end();
}

module.exports = { saveVendor };
''', "vendorClient.js": r'''const axios = require('axios');

const http = axios.create({ baseURL: 'https://vendors.example.com/api', timeout: 8000 });

async function getVendor(id) {
  const res = await http.get(`/vendors/${encodeURIComponent(id)}`);
  return res.data;
}

module.exports = { getVendor };
'''})

add("neg","javascript","axios",{"stock.js": r'''const axios = require('axios');
const mysql = require('mysql2/promise');

async function refreshStock(sku) {
  const conn = await mysql.createConnection({ host: 'db.example.com', user: 'acme' });
  const res = await axios.get(`https://warehouse.example.com/stock/${encodeURIComponent(sku)}`);
  const qty = Number(res.data.quantity);
  if (!Number.isInteger(qty) || qty < 0) {
    throw new Error('bad quantity');
  }
  await conn.query(`UPDATE stock SET qty = ${qty} WHERE sku = ?`, [sku]);
  await conn.end();
  return qty;
}

module.exports = { refreshStock };
'''})

add("pos","python","requests",{"probe.py": r'''import requests

ENDPOINTS = {
    "billing": "https://billing.internal.example.com/health",
    "search": "https://search.internal.example.com/health",
}


def probe(name):
    url = ENDPOINTS[name]
    resp = requests.get(url, timeout=3, verify=False)  §T
    return resp.status_code == 200


def probe_all():
    return {name: probe(name) for name in ENDPOINTS}


if __name__ == "__main__":
    for name, ok in probe_all().items():
        print(name, "up" if ok else "down")
'''})

add("neg","python","requests",{"runner.py": r'''import subprocess

import requests

ACTIONS = {"restart", "status", "reload"}


def fetch_task(task_id):
    resp = requests.get(f"https://tasks.example.com/v1/tasks/{int(task_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def run_task(task_id):
    task = fetch_task(task_id)
    action = task["action"]
    if action not in ACTIONS:
        raise ValueError("unknown action")
    done = subprocess.run(["acmectl", action, "--service", "worker"], check=True, capture_output=True)
    return done.stdout.decode()


def run_pending(ids):
    return [run_task(i) for i in ids]
'''})

add("neg","javascript","fetch",{"files.js": r'''const path = require('path');
const fs = require('fs/promises');

const ROOT = path.resolve('/srv/acme/uploads');

async function fetchRecord(id) {
  const res = await fetch(`https://docs.example.com/records/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('lookup failed');
  return res.json();
}

async function readAttachment(id) {
  const record = await fetchRecord(id);
  const resolved = path.resolve(ROOT, path.basename(record.file));
  if (!resolved.startsWith(ROOT + path.sep)) {
    throw new Error('outside root');
  }
  return fs.readFile(resolved);
}

module.exports = { readAttachment };
'''})

add("pos","javascript","fetch",{"reader.js": r'''const path = require('path');
const fs = require('fs/promises');

const UPLOADS = '/srv/acme/uploads';

async function fetchRecord(id) {
  const res = await fetch(`https://docs.example.com/records/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('lookup failed');
  return res.json();
}

async function readAttachment(id) {
  const record = await fetchRecord(id);
  const full = path.join(UPLOADS, record.file);
  return fs.readFile(full);  §T
}

async function listUploads() {
  return fs.readdir(UPLOADS);
}

module.exports = { readAttachment, listUploads };
'''})

add("pos","python","httpx",{"relay.py": r'''import httpx


def fetch_endpoint(account):
    r = httpx.get(f"https://registry.example.com/accounts/{account}", timeout=6.0)
    r.raise_for_status()
    return r.json()


def forward(account, payload):
    info = fetch_endpoint(account)
    resp = httpx.post(info["webhook_url"], json=payload, timeout=6.0)  §T
    return resp.status_code


def forward_batch(account, payloads):
    return [forward(account, p) for p in payloads]
'''})

add("neg","javascript","axios",{"relay.js": r'''const axios = require('axios');

const ALLOWED = 'hooks.example.com';

async function resolveTarget(account) {
  const res = await axios.get(`https://registry.example.com/accounts/${encodeURIComponent(account)}`);
  return new URL(res.data.webhook_url);
}

async function forward(account, payload) {
  const target = await resolveTarget(account);
  if (target.protocol !== 'https:' || target.hostname !== ALLOWED) {
    throw new Error('target not permitted');
  }
  const res = await axios.post(target.href, payload, { timeout: 6000 });
  return res.status;
}

module.exports = { forward };
'''})

add("pos","javascript","axios",{"convert.js": r'''const { exec } = require('child_process');
const axios = require('axios');

async function getPreset(name) {
  const res = await axios.get(`https://presets.example.com/v1/${encodeURIComponent(name)}`);
  return res.data;
}

async function convert(input, name) {
  const preset = await getPreset(name);
  return new Promise((resolve, reject) => {
    exec(`ffmpeg -i ${input} ${preset.flags} out.mp4`, (err, stdout) => {  §T
      if (err) return reject(err);
      resolve(stdout);
    });
  });
}

module.exports = { convert };
'''})

add("neg","python","requests",{"fetcher.py": r'''import requests

CA_BUNDLE = "/etc/ssl/certs/acme-internal-ca.pem"

session = requests.Session()
session.verify = CA_BUNDLE
session.headers["Accept"] = "application/json"


def fetch_status(service):
    resp = session.get(f"https://{service}.internal.example.com/status", timeout=4)
    resp.raise_for_status()
    return resp.json()


def is_ready(service):
    body = fetch_status(service)
    return body.get("state") == "ready"


def readiness_report(services):
    return {s: is_ready(s) for s in services}
'''})
