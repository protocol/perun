from flask import Blueprint, g, jsonify, request, abort
from guard import authenticated, may_view, require_agent
from store import find, by_reporter

bp = Blueprint("tickets", __name__, url_prefix="/tickets")
VIEW = ("id", "subject", "state")

def load_visible(ticket_id):
    ticket = find(ticket_id)
    if not may_view(ticket):
        abort(404)
    return ticket

@bp.get("/")
@authenticated
def mine():
    return jsonify([{k: t[k] for k in VIEW} for t in by_reporter(g.user)[:50]])

@bp.get("/<int:ticket_id>")
@authenticated
def one(ticket_id):
    t = load_visible(ticket_id)
    view = {k: t[k] for k in VIEW}
    return jsonify(view)

@bp.post("/<int:ticket_id>/comments")
@authenticated
def comment(ticket_id):
    t = load_visible(ticket_id)
    text = str(request.get_json(force=True).get("text", ""))[:500]
    if not text:
        abort(400)
    return jsonify({"ticket": t["id"], "text": text}), 201

@bp.get("/<int:ticket_id>/notes")
@authenticated
def notes(ticket_id):
    require_agent()
    t = load_visible(ticket_id)
    return jsonify({"note": t["staff_note"]})

@bp.post("/<int:ticket_id>/close")
@authenticated
def close(ticket_id):
    t = load_visible(ticket_id)
    t["state"] = "closed"
    return jsonify({"id": t["id"], "state": t["state"]})
