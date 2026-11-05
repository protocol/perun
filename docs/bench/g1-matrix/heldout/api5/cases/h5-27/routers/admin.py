from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import Tenant

router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_user)])


@router.get("/tenants")
def tenants(db: Session = Depends(get_db)):
    return [t.name for t in db.query(Tenant).all()]


@router.post("/tenants/{tenant_id}/disable")
def disable(tenant_id: int, db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    t.enabled = False
    db.commit()
    return {"id": tenant_id, "enabled": False}
