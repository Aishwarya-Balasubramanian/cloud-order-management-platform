from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Order


def create_order(db: Session, order: Order):
    db.add(order)
    db.commit()
    db.refresh(order)

    return order


def get_all_orders(db: Session):
    return db.scalars(select(Order)).all()


def get_order_by_id(db: Session, order_id: int):
    return db.get(Order, order_id)