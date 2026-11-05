import hmac
import os
import threading
import time
from contextlib import closing
from flask import Flask, jsonify, abort, request
from catalog import connect, sync, price_of
from vendor import VendorError

app = Flask(__name__)
sync_lock = threading.Lock()
hits = {}
window = [0]

@app.before_request
def limit():
    if time.time() > window[0] or len(hits) > 10000:
        hits.clear()
        window[0] = time.time() + 60
    hits[request.remote_addr] = hits.get(request.remote_addr, 0) + 1
    if hits[request.remote_addr] > 60:
        abort(429)

@app.post("/sync/<category>")
def run_sync(category):
    admin = os.environ.get("ADMIN_KEY")
    if not admin or not hmac.compare_digest(request.headers.get("X-Admin-Key", "").encode(), admin.encode()):
        abort(403)
    if not category.isalnum() or len(category) > 20:
        abort(400)
    if not sync_lock.acquire(blocking=False):
        abort(409)
    try:
        with closing(connect()) as db:
            return jsonify({"synced": sync(db, category)})
    except VendorError:
        abort(502)
    finally:
        sync_lock.release()

@app.get("/price/<sku>")
def price(sku):
    with closing(connect()) as db:
        value = price_of(db, sku)
    if value is None:
        abort(404)
    return jsonify({"sku": sku, "price": value})
