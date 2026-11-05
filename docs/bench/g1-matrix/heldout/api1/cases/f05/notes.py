from flask import Blueprint, abort, jsonify
from flask_login import current_user, login_required

from .models import Note, db

bp = Blueprint("notes", __name__)


@bp.get("/notes/<int:note_id>")
@login_required
def show_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return jsonify(note.to_dict())


@bp.delete("/notes/<int:note_id>")
@login_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        abort(403)
    db.session.delete(note)
    db.session.commit()
    return "", 204
