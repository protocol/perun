import logging
import os
from functools import wraps
from urllib.parse import urlparse

import requests
from flask import Flask, abort, g, jsonify, request

from store import FLAGS, MATCHES, TEAMS, TOKENS

app = Flask(__name__)
log = logging.getLogger("scoreboard")

FEED = "https://feed.vendor.example.com"
FEED_KEY = os.environ["FEED_KEY"]
BADGE_HOSTS = {"badges.example.com", "static.example.com"}


def current_user():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return TOKENS.get(token)


@app.before_request
def gate():
    # Global gate: every /api/ path needs a session except the partner prefix.
    if not request.path.startswith("/api/") or request.path.startswith("/api/open/"):
        return None
    user = current_user()
    if user is None:
        abort(401)
    g.user = user
    return None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            abort(401)
        g.user = user
        return view(*args, **kwargs)

    return wrapper


def require_role(role):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                abort(401)
            if user["role"] != role:
                abort(403)
            g.user = user
            return view(*args, **kwargs)

        return wrapper

    return deco


@app.get("/api/open/standings")  # @@R GET /api/open/standings 0 ; T positive missing_authn partner prefix skipped by the before_request gate returns full standings with owner ids
def open_standings():
    rows = sorted(TEAMS.values(), key=lambda t: -t["score"])
    out = []
    for team in rows:
        out.append({"name": team["name"], "score": team["score"], "owner_id": team["owner_id"]})
    return jsonify(out)


@app.get("/api/teams")  # @@R GET /api/teams 1
def list_teams():
    mine = [t for t in TEAMS.values() if t["owner_id"] == g.user["id"]]
    return jsonify(mine)


@app.get("/api/matches/<int:match_id>")  # @@R GET /api/matches/<int:match_id> 1 ; T decoy missing_object_check gate plus owner comparison
def get_match(match_id):
    match = MATCHES.get(match_id)
    if match is None or match["owner_id"] != g.user["id"]:
        abort(404)
    return jsonify(match)


@app.get("/api/matches/<int:match_id>/notes")  # @@R GET /api/matches/<int:match_id>/notes 0 ; T positive missing_object_check any logged-in user can read any match notes
def match_notes(match_id):
    match = MATCHES.get(match_id)
    if match is None:
        abort(404)
    return jsonify({"id": match["id"], "notes": match["notes"]})


@app.post("/api/feed/refresh")  # @@R POST /api/feed/refresh 1
def refresh_feed():
    resp = requests.get(
        FEED + "/v1/scores",
        headers={"X-Api-Key": FEED_KEY},
        timeout=5,
        verify=False,  # @@T positive tls_off certificate verification disabled
    )
    return jsonify(resp.json())


@app.get("/api/teams/count")  # @@R GET /api/teams/count 1
def team_count():
    mine = [t for t in TEAMS.values() if t["owner_id"] == g.user["id"]]
    wins = sum(1 for t in mine if t["score"] > 40)
    return jsonify({"count": len(mine), "leading": wins})


@app.delete("/api/teams/<int:team_id>")  # @@R DELETE /api/teams/<int:team_id> 1 ; T decoy missing_object_check delete limited to the owner
def delete_team(team_id):
    team = TEAMS.get(team_id)
    if team is None or team["owner_id"] != g.user["id"]:
        abort(404)
    del TEAMS[team_id]
    return "", 204


@app.put("/api/teams/<int:team_id>")  # @@R PUT /api/teams/<int:team_id> 0 ; T positive missing_object_check rename without checking the team belongs to the caller
def rename_team(team_id):
    team = TEAMS.get(team_id)
    if team is None:
        abort(404)
    team["name"] = str(request.get_json().get("name", team["name"]))
    return jsonify(team)


@app.get("/api/badge")  # @@R GET /api/badge 1
def badge():
    target = request.args.get("url", "")
    resp = requests.get(target, timeout=5)  # @@T positive ssrf caller-controlled URL fetched server side
    return jsonify({"type": resp.headers.get("content-type"), "bytes": len(resp.content)})


@app.get("/api/badge/safe")  # @@R GET /api/badge/safe 1
def badge_safe():
    target = urlparse(request.args.get("url", ""))
    if target.scheme != "https" or target.hostname not in BADGE_HOSTS:
        abort(400)
    resp = requests.get(target.geturl(), timeout=5, allow_redirects=False)  # @@T decoy ssrf https plus host allowlist plus no redirects
    return jsonify({"type": resp.headers.get("content-type")})


@app.get("/api/feed/teams/<int:team_id>")  # @@R GET /api/feed/teams/<int:team_id> 1
def feed_team(team_id):
    if team_id not in TEAMS:
        abort(404)
    resp = requests.get(FEED + f"/v1/teams/{team_id}", headers={"X-Api-Key": FEED_KEY})  # @@T positive no_timeout outbound call without a timeout
    return jsonify(resp.json())


@app.get("/api/feed/teams/<int:team_id>/form")  # @@R GET /api/feed/teams/<int:team_id>/form 1
def feed_form(team_id):
    if team_id not in TEAMS:
        abort(404)
    resp = requests.get(FEED + f"/v1/teams/{team_id}/form", headers={"X-Api-Key": FEED_KEY}, timeout=5)  # @@T decoy secret_in_url key sent in a header, with timeout
    return jsonify(resp.json())


@app.get("/api/feed/teams/<int:team_id>/history")  # @@R GET /api/feed/teams/<int:team_id>/history 1
def feed_history(team_id):
    if team_id not in TEAMS:
        abort(404)
    url = FEED + f"/v1/teams/{team_id}/history?key={FEED_KEY}"  # @@T positive secret_in_url API key in the query string
    resp = requests.get(url, timeout=5)
    return jsonify(resp.json())


@app.get("/api/feed/teams/<int:team_id>/odds")  # @@R GET /api/feed/teams/<int:team_id>/odds 1
def feed_odds(team_id):
    if team_id not in TEAMS:
        abort(404)
    log.info("odds call using key %s", FEED_KEY)  # @@T positive secret_in_log key written to the log
    resp = requests.get(FEED + f"/v1/teams/{team_id}/odds", headers={"X-Api-Key": FEED_KEY}, timeout=5)
    return jsonify(resp.json())


@app.get("/api/feed/teams/<int:team_id>/roster")  # @@R GET /api/feed/teams/<int:team_id>/roster 1
def feed_roster(team_id):
    if team_id not in TEAMS:
        abort(404)
    resp = requests.get(FEED + f"/v1/teams/{team_id}/roster", headers={"X-Api-Key": FEED_KEY}, timeout=5)
    log.info("roster call ok team=%s status=%s", team_id, resp.status_code)  # @@T decoy secret_in_log log line carries no secret
    return jsonify(resp.json())


@app.get("/api/matches")  # @@R GET /api/matches 1
def list_matches():
    mine = [m for m in MATCHES.values() if m["owner_id"] == g.user["id"]]
    mine.sort(key=lambda m: m["id"])
    return jsonify(mine)


# Staff pages sit outside /api and use per-route decorators instead of the gate.
@app.get("/admin/audit")  # @@R GET /admin/audit 0 ; T positive missing_authn staff audit trail with no decorator and outside the gate
def admin_audit():
    rows = [{"id": m["id"], "owner_id": m["owner_id"]} for m in MATCHES.values()]
    return jsonify(rows)


@app.post("/admin/flags/<name>")  # @@R POST /admin/flags/<name> 0 ; T positive missing_authz login required but any member can flip feature flags
@login_required
def set_flag(name):
    if name not in FLAGS:
        abort(404)
    FLAGS[name] = bool(request.get_json().get("on"))
    return jsonify(FLAGS)


@app.get("/admin/overview")  # @@R GET /admin/overview 1 ; T decoy missing_authz admin role enforced by decorator
@require_role("admin")
def admin_overview():
    return jsonify({"teams": len(TEAMS), "matches": len(MATCHES)})


@app.post("/admin/recount")  # @@R POST /admin/recount 1 ; T decoy missing_authz admin role enforced by decorator
@require_role("admin")
def admin_recount():
    total = sum(t["score"] for t in TEAMS.values())
    return jsonify({"total": total}), 202


@app.get("/admin/me/matches")  # @@R GET /admin/me/matches 1 ; T decoy missing_authn login_required decorator, results limited to the caller
@login_required
def my_matches():
    mine = [m for m in MATCHES.values() if m["owner_id"] == g.user["id"]]
    return jsonify(mine)


from extras import extras  # noqa: E402

app.secret_key = os.environ['SESSION_KEY']
app.register_blueprint(extras)
