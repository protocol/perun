from databases import Database
from fastapi import APIRouter, Depends, HTTPException

from .security import current_user

database = Database("postgresql://localhost/acme")
router = APIRouter()


@router.get("/messages/{message_id}")
async def get_message(message_id: int, user=Depends(current_user)):
    row = await database.fetch_one(
        "SELECT * FROM messages WHERE id = :id AND recipient_id = :uid",
        {"id": message_id, "uid": user.id},
    )
    if row is None:
        raise HTTPException(status_code=404)
    return dict(row)


@router.get("/messages/{message_id}/attachments")
async def attachments(message_id: int, user=Depends(current_user)):
    msg = await database.fetch_one("SELECT * FROM messages WHERE id = :id", {"id": message_id})
    if msg is None:
        raise HTTPException(status_code=404)
    return await database.fetch_all(
        "SELECT * FROM attachments WHERE message_id = :id", {"id": msg["id"]}
    )
