from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .db import engine
from .models import Order
from .security import get_user

router = APIRouter()


def session():
    with Session(engine) as s:
        yield s


@router.get("/orders")
def my_orders(s: Session = Depends(session), user=Depends(get_user)):
    return s.exec(select(Order).where(Order.user_id == user.id)).all()


@router.post("/orders/refund")
def refund(body: dict, s: Session = Depends(session), user=Depends(get_user)):
    order = s.get(Order, body["order_id"])
    if order is None:
        raise HTTPException(status_code=404)
    order.status = "refunded"
    s.add(order)
    s.commit()
    return order
