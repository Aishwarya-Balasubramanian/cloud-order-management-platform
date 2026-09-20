import json
import logging
import os
import time

import boto3
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.integrations.fulfillment_client import (
    FulfillmentClient,
    NonRetryableFulfillmentError,
    RetryableFulfillmentError,
)
from app.models.models import Order, ProcessedEvent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

QUEUE_URL = os.getenv("ORDER_QUEUE_URL")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

FULFILLMENT_API_URL = os.getenv(
    "FULFILLMENT_API_URL",
    "http://localhost:9000",
)

EXPECTED_EVENT_TYPE = "OrderCreated"
FULFILLABLE_ORDER_STATUS = "PENDING"


def select_order_by_number(order_number):
    return select(Order).where(
        Order.order_number == order_number
    )


def process_message(message):
    """
    Process one OrderCreated event.

    Delivery semantics:
    - SQS provides at-least-once delivery.
    - ProcessedEvent provides durable duplicate detection.
    - order_number is propagated to the fulfillment API as its
      idempotency key by FulfillmentClient.
    - Exactly-once execution is not claimed because PostgreSQL and
      the external fulfillment service do not share one transaction.
    """

    try:
        event = json.loads(message["Body"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise NonRetryableFulfillmentError(
            "Message body is not valid JSON"
        ) from exc

    event_id = event.get("event_id")
    event_type = event.get("event_type")
    order_number = event.get("order_number")

    if event_type != EXPECTED_EVENT_TYPE:
        raise NonRetryableFulfillmentError(
            f"Unsupported event type: {event_type}"
        )

    if not event_id:
        raise NonRetryableFulfillmentError(
            "OrderCreated event missing event_id"
        )

    if not order_number:
        raise NonRetryableFulfillmentError(
            "OrderCreated event missing order_number"
        )

    db = SessionLocal()

    try:
        already_processed = db.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == event_id
            )
        )

        if already_processed:
            logger.info(
                "duplicate_event_skipped "
                "event_id=%s "
                "order_number=%s",
                event_id,
                order_number,
            )
            return

        order = db.scalar(
            select_order_by_number(order_number)
        )

        if order is None:
            raise NonRetryableFulfillmentError(
                f"Order {order_number} does not exist"
            )

        # Prevent stale or unexpected OrderCreated events from
        # moving an order backwards in its lifecycle.
        if order.status != FULFILLABLE_ORDER_STATUS:
            raise NonRetryableFulfillmentError(
                f"Order {order_number} cannot be fulfilled "
                f"from status {order.status}"
            )

        client = FulfillmentClient(
            FULFILLMENT_API_URL
        )

        # This external side effect cannot participate in the
        # PostgreSQL transaction. FulfillmentClient therefore sends
        # order_number as the downstream Idempotency-Key.
        client.create_fulfillment(order)

        order.status = "CONFIRMED"

        db.add(
            ProcessedEvent(
                event_id=event_id,
                event_type=event_type,
            )
        )

        try:
            # Order state and durable processed marker commit
            # atomically inside PostgreSQL.
            db.commit()

        except IntegrityError as exc:
            db.rollback()

            # Another worker may have committed the same event first.
            # The downstream idempotency key is still required to
            # protect the external fulfillment side effect.
            duplicate = db.scalar(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id == event_id
                )
            )

            if duplicate:
                logger.warning(
                    "concurrent_duplicate_event_detected "
                    "event_id=%s "
                    "order_number=%s",
                    event_id,
                    order_number,
                )
                return

            raise exc

        logger.info(
            "order_fulfillment_confirmed "
            "event_id=%s "
            "order_id=%s "
            "order_number=%s",
            event_id,
            order.id,
            order.order_number,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def run_worker():
    if not QUEUE_URL:
        logger.warning(
            "ORDER_QUEUE_URL not configured; worker will not start"
        )
        return

    sqs = boto3.client(
        "sqs",
        region_name=AWS_REGION,
    )

    logger.info("order_worker_started")

    while True:
        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=5,
            WaitTimeSeconds=20,
            VisibilityTimeout=30,
        )

        messages = response.get(
            "Messages",
            [],
        )

        for message in messages:
            try:
                process_message(message)

                sqs.delete_message(
                    QueueUrl=QUEUE_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                )

            except RetryableFulfillmentError as exc:
                # Do not delete.
                # SQS will make the message visible again and the
                # redrive policy eventually sends repeated failures
                # to the DLQ.
                logger.warning(
                    "retryable_fulfillment_failure error=%s",
                    str(exc),
                )

            except NonRetryableFulfillmentError as exc:
                # Intentionally leave the message undeleted so the
                # configured SQS redrive policy captures poison
                # messages in the DLQ for investigation.
                logger.error(
                    "non_retryable_fulfillment_failure error=%s",
                    str(exc),
                )

            except Exception:
                # Unknown infrastructure/application failures are
                # also retried through SQS redelivery.
                logger.exception(
                    "unexpected_worker_failure"
                )

        time.sleep(1)


if __name__ == "__main__":
    run_worker()