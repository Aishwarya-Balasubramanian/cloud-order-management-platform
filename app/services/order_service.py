import json
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Order, OrderItem, OutboxEvent
from app.repositories.customer_repository import get_customer_by_id
from app.repositories.product_repository import get_product_by_id
from app.repositories.order_repository import get_order_by_id


ALLOWED_TRANSITIONS = {
    "PENDING": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"PROCESSING", "CANCELLED"},
    "PROCESSING": {"SHIPPED"},
    "SHIPPED": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def create_order(db: Session, order_request):
    customer = get_customer_by_id(
        db,
        order_request.customer_id,
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {order_request.customer_id} not found",
        )

    if not customer.active:
        raise HTTPException(
            status_code=409,
            detail="Customer is inactive",
        )

    order_items = []
    total_amount = Decimal("0")

    for requested_item in order_request.items:
        product = get_product_by_id(
            db,
            requested_item.product_id,
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {requested_item.product_id} not found",
            )

        if not product.active:
            raise HTTPException(
                status_code=409,
                detail=f"Product {product.id} is inactive",
            )

        line_total = product.price * requested_item.quantity
        total_amount += line_total

        order_items.append(
            OrderItem(
                product_id=product.id,
                sku=product.sku,
                quantity=requested_item.quantity,
                unit_price=product.price,
                line_total=line_total,
            )
        )

    order_number = f"ORD-{uuid4().hex[:12].upper()}"

    new_order = Order(
        order_number=order_number,
        customer_id=order_request.customer_id,
        status="PENDING",
        total_amount=total_amount,
        items=order_items,
    )

    event_id = str(uuid4())

    event_payload = {
        "event_id": event_id,
        "event_type": "OrderCreated",
        "order_number": order_number,
        "customer_id": order_request.customer_id,
        "total_amount": str(total_amount),
    }

    outbox_event = OutboxEvent(
        event_id=event_id,
        event_type="OrderCreated",
        aggregate_type="Order",
        aggregate_id=order_number,
        payload=json.dumps(event_payload),
        processed=False,
    )

    try:
        # Both records participate in the SAME database transaction.
        db.add(new_order)
        db.add(outbox_event)

        db.commit()

        db.refresh(new_order)

    except Exception:
        db.rollback()
        raise

    return new_order


def change_order_status(
    db: Session,
    order_id: int,
    new_status: str,
):
    order = get_order_by_id(db, order_id)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    current_status = order.status

    if new_status not in ALLOWED_TRANSITIONS[current_status]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot change order from "
                f"{current_status} to {new_status}"
            ),
        )

    order.status = new_status

    try:
        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    return order