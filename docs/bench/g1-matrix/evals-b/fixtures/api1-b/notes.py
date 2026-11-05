from fastapi import APIRouter, Depends, HTTPException

from .db import get_db
from .auth import current_user

router = APIRouter()


@router.get("/notes/{note_id}")
def read_note(note_id: int, user=Depends(current_user), db=Depends(get_db)):
    row = db.execute(
        "SELECT id, title, body FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": row[0], "title": row[1], "body": row[2]}


@router.get("/notes")
def list_notes(user=Depends(current_user), db=Depends(get_db)):
    rows = db.execute(
        "SELECT id, title FROM notes WHERE owner_id = ?", (user.id,)
    ).fetchall()
    return [{"id": r[0], "title": r[1]} for r in rows]
