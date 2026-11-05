from flask import Blueprint, g, jsonify, request, abort
from authz import login_required, can_read, can_write
from models import get_doc, docs_for

bp = Blueprint("docs", __name__, url_prefix="/docs")

@bp.get("/")
@login_required
def index():
    return jsonify([{"id": d.id, "title": d.title} for d in docs_for(g.user)][:50])

@bp.get("/<int:doc_id>")
@login_required
def show(doc_id):
    doc = get_doc(doc_id)
    if not can_read(g.user, doc):
        abort(404)
    return jsonify({"id": doc.id, "title": doc.title, "body": doc.body})

@bp.patch("/<int:doc_id>")
@login_required
def update(doc_id):
    doc = get_doc(doc_id)
    if not can_write(g.user, doc):
        abort(404)
    title = str(request.get_json(force=True).get("title", ""))[:120]
    if not title:
        abort(400)
    doc.title = title
    return jsonify({"id": doc.id, "title": doc.title})

@bp.post("/<int:doc_id>/share")
@login_required
def share(doc_id):
    doc = get_doc(doc_id)
    target = str(request.get_json(force=True).get("user", ""))[:40]
    if doc is None or not target:
        abort(404)
    if target not in doc.shared_with:
        doc.shared_with.append(target)
    return jsonify({"id": doc.id, "shared_with": doc.shared_with})

@bp.delete("/<int:doc_id>")
@login_required
def remove(doc_id):
    doc = get_doc(doc_id)
    if not can_write(g.user, doc):
        abort(404)
    return "", 204
