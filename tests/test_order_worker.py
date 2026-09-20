from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import json
from app.integrations.fulfillment_client import RetryableFulfillmentError
from app.models.models import Order, ProcessedEvent
from app.workers.order_worker import process_message


def make_message():
    return {
        "Body": """
        {
            "event_id": "11111111-1111-1111-1111-111111111111",
            "event_type": "OrderCreated",
            "order_number": "ORD-TEST-001",
            "customer_id": 1,
            "total_amount": "50.00"
        }
        """
    }


def make_order():
    return Order(
        id=1,
        order_number="ORD-TEST-001",
        customer_id=1,
        status="PENDING",
        total_amount=Decimal("50.00"),
    )


@patch("app.workers.order_worker.SessionLocal")
def test_duplicate_event_skips_fulfillment(mock_session_local):
    db = MagicMock()
    mock_session_local.return_value = db

    existing_event = ProcessedEvent(
        event_id="11111111-1111-1111-1111-111111111111",
        event_type="OrderCreated",
    )

    db.scalar.return_value = existing_event

    with patch(
        "app.workers.order_worker.FulfillmentClient"
    ) as mock_client:
        process_message(make_message())

        mock_client.assert_not_called()

    db.commit.assert_not_called()


@patch("app.workers.order_worker.SessionLocal")
def test_successful_event_records_processed_event(
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    order = make_order()

    # First scalar(): processed-event lookup.
    # Second scalar(): order lookup.
    db.scalar.side_effect = [
        None,
        order,
    ]

    with patch(
        "app.workers.order_worker.FulfillmentClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value

        process_message(make_message())

        mock_client.create_fulfillment.assert_called_once_with(
            order
        )

    assert order.status == "CONFIRMED"

    db.add.assert_called_once()

    processed_event = db.add.call_args.args[0]

    assert isinstance(processed_event, ProcessedEvent)

    assert (
        processed_event.event_id
        == "11111111-1111-1111-1111-111111111111"
    )

    assert processed_event.event_type == "OrderCreated"

    db.commit.assert_called_once()


@patch("app.workers.order_worker.SessionLocal")
def test_fulfillment_failure_does_not_mark_processed(
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    order = make_order()

    db.scalar.side_effect = [
        None,
        order,
    ]

    with patch(
        "app.workers.order_worker.FulfillmentClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value

        mock_client.create_fulfillment.side_effect = (
            RetryableFulfillmentError(
                "Fulfillment service unavailable"
            )
        )

        with pytest.raises(RetryableFulfillmentError):
            process_message(make_message())

    assert order.status == "PENDING"

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_non_pending_order_does_not_call_fulfillment(monkeypatch):
    from unittest.mock import MagicMock

    from app.workers import order_worker

    order = MagicMock()
    order.id = 1
    order.order_number = "ORD-TEST-001"
    order.status = "CONFIRMED"

    db = MagicMock()

    # First scalar(): ProcessedEvent lookup -> not processed
    # Second scalar(): Order lookup -> existing CONFIRMED order
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
        lambda *_: fulfillment,
    )

    message = {
        "Body": json.dumps(
            {
                "event_id": "event-status-test",
                "event_type": "OrderCreated",
                "order_number": "ORD-TEST-001",
            }
        )
    }

    with pytest.raises(
        order_worker.NonRetryableFulfillmentError
    ):
        order_worker.process_message(message)

    fulfillment.create_fulfillment.assert_not_called()
    db.rollback.assert_called()    