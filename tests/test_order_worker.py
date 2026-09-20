import json
from unittest.mock import MagicMock

import pytest

from app.integrations.fulfillment_client import RetryableFulfillmentError
from app.workers import order_worker


def make_message(
    event_id="event-123",
    event_type="OrderCreated",
    order_number="ORD-001",
):
    return {
        "Body": json.dumps(
            {
                "event_id": event_id,
                "event_type": event_type,
                "order_number": order_number,
            }
        )
    }


def make_order(status="PENDING"):
    order = MagicMock()
    order.id = 1
    order.order_number = "ORD-001"
    order.status = status
    return order


def test_duplicate_event_skips_fulfillment(monkeypatch):
    db = MagicMock()

    processed_event = MagicMock()

    # First scalar call checks ProcessedEvent.
    db.scalar.return_value = processed_event

    monkeypatch.setattr(
        order_worker,
        "SessionLocal",
        lambda: db,
    )

    fulfillment = MagicMock()

    monkeypatch.setattr(
        order_worker,
        "FulfillmentClient",
        lambda *_args, **_kwargs: fulfillment,
    )

    order_worker.process_message(
        make_message()
    )

    fulfillment.create_fulfillment.assert_not_called()
    db.commit.assert_not_called()
    db.close.assert_called_once()


def test_successful_event_records_processed_event(monkeypatch):
    db = MagicMock()

    order = make_order(status="PENDING")

    # First scalar:
    #   ProcessedEvent lookup -> None
    #
    # Second scalar:
    #   Order lookup -> order
    db.scalar.side_effect = [
        None,
        order,
    ]

    monkeypatch.setattr(
        order_worker,
        "SessionLocal",
        lambda: db,
    )

    fulfillment = MagicMock()

    monkeypatch.setattr(
        order_worker,
        "FulfillmentClient",
        lambda *_args, **_kwargs: fulfillment,
    )

    order_worker.process_message(
        make_message()
    )

    fulfillment.create_fulfillment.assert_called_once_with(
        order
    )

    assert order.status == "CONFIRMED"

    db.add.assert_called_once()

    processed_event = db.add.call_args.args[0]

    assert processed_event.event_id == "event-123"
    assert processed_event.event_type == "OrderCreated"

    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_fulfillment_failure_does_not_mark_processed(
    monkeypatch,
):
    db = MagicMock()

    order = make_order(status="PENDING")

    db.scalar.side_effect = [
        None,
        order,
    ]

    monkeypatch.setattr(
        order_worker,
        "SessionLocal",
        lambda: db,
    )

    fulfillment = MagicMock()

    fulfillment.create_fulfillment.side_effect = (
        RetryableFulfillmentError(
            "temporary fulfillment failure"
        )
    )

    monkeypatch.setattr(
        order_worker,
        "FulfillmentClient",
        lambda *_args, **_kwargs: fulfillment,
    )

    with pytest.raises(
        RetryableFulfillmentError
    ):
        order_worker.process_message(
            make_message()
        )

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_non_pending_order_does_not_call_fulfillment(
    monkeypatch,
):
    db = MagicMock()

    order = make_order(status="CONFIRMED")

    # Event has not been processed before,
    # but the order has already moved beyond PENDING.
    db.scalar.side_effect = [
        None,
        order,
    ]

    monkeypatch.setattr(
        order_worker,
        "SessionLocal",
        lambda: db,
    )

    fulfillment = MagicMock()

    monkeypatch.setattr(
        order_worker,
        "FulfillmentClient",
        lambda *_args, **_kwargs: fulfillment,
    )

    with pytest.raises(
        order_worker.NonRetryableFulfillmentError
    ):
        order_worker.process_message(
            make_message(
                event_id="event-status-test-001"
            )
        )

    fulfillment.create_fulfillment.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    db.close.assert_called_once()