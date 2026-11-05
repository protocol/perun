from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session
from deps import get_db, current_identity
from models import Invite

app = FastAPI()
auth = Depends(current_identity)


@app.get("/v1/invites/{invite_id}")
def read_invite(invite_id: int, db: Session = Depends(get_db), who=auth):
    inv = db.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404)
    return {"id": inv.id, "email": inv.email}


@app.delete("/admin/invites/{invite_id}")
def drop_invite(invite_id: int, db: Session = Depends(get_db), who=auth):
    inv = db.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404)
    db.delete(inv)
    db.commit()
    return {"deleted": invite_id}
