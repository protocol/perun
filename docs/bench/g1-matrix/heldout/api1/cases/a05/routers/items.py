from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Item

router = APIRouter(prefix="/items")


@router.get("/{item_id}")
def read_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(Item).filter(Item.id == item_id, Item.owner_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404)
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.get(Item, item_id)
    if item is None or item.owner_id != user.id:
        raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return {"deleted": item_id}
