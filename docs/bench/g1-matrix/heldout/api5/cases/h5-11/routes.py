from fastapi import APIRouter, Depends, Security
from sqlmodel import Session
from deps import get_session, get_current_user
from models import PermissionGrant

router = APIRouter(tags=["access"])


@router.get("/permissions")
def mine(user=Security(get_current_user, scopes=["me"]), session: Session = Depends(get_session)):
    return session.query(PermissionGrant).filter_by(user_id=user.id).all()


@router.post("/permissions/grant")
def grant(user_id: int, name: str, user=Security(get_current_user, scopes=["admin"]),
          session: Session = Depends(get_session)):
    session.add(PermissionGrant(user_id=user_id, name=name))
    session.commit()
    return {"granted": name}
