from sqlalchemy.orm import Session

from app.models.models import Customer


def create_customer(db: Session, name: str, email: str):
    customer = Customer(
        name=name,
        email=email,
        active=True
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    return customer


def get_customer_by_id(db: Session, customer_id: int):
    return db.get(Customer, customer_id)