from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product


def create_product(db: Session, sku: str, name: str, price):
    product = Product(
        sku=sku,
        name=name,
        price=price,
        active=True
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


def get_all_products(db: Session):
    return db.scalars(select(Product)).all()


def get_product_by_id(db: Session, product_id: int):
    return db.get(Product, product_id)