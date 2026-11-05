from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import Order, User

app = FastAPI()


class RoleChecker:
    def __init__(self, allowed):
        self.allowed = set(allowed)

    def __call__(self, user: User = Depends(get_current_user)):
        if user.role not in self.allowed:
            raise HTTPException(status_code=403)
        return user


@app.get("/orders")
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.user_id == user.id).all()


@app.post("/admin/orders/{order_id}/refund")
def refund(order_id: int, user=Depends(RoleChecker(["admin", "support"])), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    order.refunded = True
    db.commit()
    return {"id": order.id}
