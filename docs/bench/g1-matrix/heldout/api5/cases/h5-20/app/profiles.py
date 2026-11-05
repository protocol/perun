from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models import Profile
from app.schemas import ProfilePatch

router = APIRouter()


@router.get("/profiles/{profile_id}")
def read(profile_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.get(Profile, profile_id)


@router.patch("/profiles/{profile_id}")
def edit(profile_id: int, patch: ProfilePatch, user=Depends(get_current_user),
         db: Session = Depends(get_db)):
    p = db.get(Profile, profile_id)
    if p is None:
        raise HTTPException(404)
    p.display_name = patch.display_name
    db.commit()
    return p
