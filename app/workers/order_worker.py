import json
import logging
import os
import time

import boto3
from sqlalchemy import select

from app.database import SessionLocal
from app.integrations.fulfillment_client import (
    FulfillmentClient,
    NonRetryableFulfillmentError,
    RetryableFulfillmentError,
)
from app.models.models import ProcessedEvent
from app.repositories.order_repository import get_order_by_id


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


def process_message(message):
    event = json.loads(message["Body"])

    event_id = event.get("event_id")
    event_type = event.get("event_type")
    order_number = event.get("order_number")

    if event_type != "OrderCreated":
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
        # Durable duplicate detection.
        already_processed = db.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == event_id
            )
        )

        if already_processed:
            logger.info(
                "duplicate_event_skipped event_id=%s",
                event_id,
            )
            return

        order = db.scalar(
            select_order_by_number(order_number)
        )

        if order is None:
            raise NonRetryableFulfillmentError(
                f"Order {order_number} does not exist"
            )

        client = FulfillmentClient(FULFILLMENT_API_URL)

        client.create_fulfillment(order)

        # The external service accepted fulfillment.
        order.status = "CONFIRMED"

        processed_event = ProcessedEvent(
            event_id=event_id,
            event_type=event_type,
        )

        db.add(processed_event)

        # Order state + processed marker commit together.
        db.commit()

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


def select_order_by_number(order_number):
    from app.models.models import Order

    return select(Order).where(
        Order.order_number == order_number
    )


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

        messages = response.get("Messages", [])

        for message in messages:
            try:
                process_message(message)

                sqs.delete_message(
                    QueueUrl=QUEUE_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                )

            except RetryableFulfillmentError as exc:
                logger.warning(
                    "retryable_fulfillment_failure error=%s",
                    str(exc),
                )

            except NonRetryableFulfillmentError as exc:
                logger.error(
                    "non_retryable_fulfillment_failure error=%s",
                    str(exc),
                )

            except Exception:
                logger.exception(
                    "unexpected_worker_failure"
                )

        time.sleep(1)


if __name__ == "__main__":
    run_worker()