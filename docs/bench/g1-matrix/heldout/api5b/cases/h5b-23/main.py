from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import Coupon, User

app = FastAPI()
admin = APIRouter(prefix="/admin", dependencies=[Depends(get_current_user)])


@admin.post("/coupons")
def add_coupon(code: str, percent: int, db: Session = Depends(get_db)):
    c = Coupon(code=code, percent=percent)
    db.add(c)
    db.commit()
    return {"id": c.id}


@app.get("/coupons/{code}")
def lookup(code: str, db: Session = Depends(get_db)):
    return db.query(Coupon).filter_by(code=code).first()


app.include_router(admin)
