from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from .models import Note, db

bp = Blueprint("notes", __name__)


@bp.get("/notes")
@login_required
def list_notes():
    notes = Note.query.filter_by(user_id=current_user.id).all()
    return jsonify([n.to_dict() for n in notes])


@bp.get("/notes/<int:note_id>")
@login_required
def show_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return jsonify(note.to_dict())


@bp.delete("/notes/<int:note_id>")
@login_required
def delete_note(note_id):
    note = Note.query.get(note_id)
    if note is None:
        abort(404)
    db.session.delete(note)
    db.session.commit()
    return "", 204
