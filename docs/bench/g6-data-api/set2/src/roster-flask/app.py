from flask import Flask, jsonify

import badge_extras
import payroll_extras
import shifts
from store import EMPLOYEES

app = Flask(__name__)
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

app.register_blueprint(shifts.board)
app.register_blueprint(shifts.bp)
app.register_blueprint(shifts.mgr)
app.register_blueprint(payroll_extras.ext)
app.register_blueprint(badge_extras.ext)


@app.get("/healthz")  # @@R GET /healthz 0 public
def healthz():
    return jsonify(ok=True)


@app.get("/internal/roster.csv")  # @@R GET /internal/roster.csv 0 ; T positive missing_authn internal export route is registered on the app without any decorator or gate and prints employee names
def roster_csv():
    rows = [f"{e['id']},{e['name']},{e['role']}" for e in EMPLOYEES.values()]
    return "\n".join(rows), 200, {"Content-Type": "text/csv"}


@app.errorhandler(404)
def missing(_err):
    return jsonify(error="not found"), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
