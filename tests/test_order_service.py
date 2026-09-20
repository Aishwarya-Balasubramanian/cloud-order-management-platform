from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.models import Customer, Product, OutboxEvent
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import create_order


def test_create_order_customer_not_found():
    db = MagicMock()

    order_request = OrderCreate(
        customer_id=999,
        items=[
            OrderItemCreate(
                product_id=1,
                quantity=1,
            )
        ],
    )

    with patch(
        "app.services.order_service.get_customer_by_id",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            create_order(db, order_request)

    assert exc.value.status_code == 404
    assert "Customer 999 not found" in exc.value.detail


def test_create_order_calculates_server_price():
    db = MagicMock()

    customer = Customer(
        id=1,
        name="Test Customer",
        email="customer@example.com",
        active=True,
    )

    product = Product(
        id=10,
        sku="SKU-100",
        name="Test Product",
        price=Decimal("25.00"),
        active=True,
    )

    order_request = OrderCreate(
        customer_id=1,
        items=[
            OrderItemCreate(
                product_id=10,
                quantity=2,
            )
        ],
    )

    with (
        patch(
            "app.services.order_service.get_customer_by_id",
            return_value=customer,
        ),
        patch(
            "app.services.order_service.get_product_by_id",
            return_value=product,
        ),
    ):
        order = create_order(db, order_request)

    assert order.customer_id == 1
    assert order.status == "PENDING"
    assert order.total_amount == Decimal("50.00")

    assert len(order.items) == 1
    assert order.items[0].product_id == 10
    assert order.items[0].quantity == 2
    assert order.items[0].unit_price == Decimal("25.00")
    assert order.items[0].line_total == Decimal("50.00")

    # Order and OutboxEvent must be persisted before one commit.
    assert db.add.call_count == 2

    added_objects = [
        call.args[0]
        for call in db.add.call_args_list
    ]

    outbox_events = [
        obj
        for obj in added_objects
        if isinstance(obj, OutboxEvent)
    ]

    assert len(outbox_events) == 1

    outbox_event = outbox_events[0]

    assert outbox_event.event_type == "OrderCreated"
    assert outbox_event.aggregate_type == "Order"
    assert outbox_event.aggregate_id == order.order_number
    assert outbox_event.processed is False
    assert order.order_number in outbox_event.payload

    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(order)