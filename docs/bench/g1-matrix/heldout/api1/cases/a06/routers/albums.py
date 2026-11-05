from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Album

router = APIRouter(prefix="/albums")


def owned_album(album_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    album = db.get(Album, album_id)
    if album is None or album.user_id != user.id:
        raise HTTPException(status_code=404)
    return album


@router.get("/{album_id}")
def read_album(album=Depends(owned_album)):
    return album


@router.patch("/{album_id}")
def rename_album(title: str, album=Depends(owned_album), db: Session = Depends(get_db)):
    album.title = title
    db.commit()
    return album


@router.get("")
def list_albums(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Album).filter(Album.user_id == user.id).all()
