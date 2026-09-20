import logging
import os
import time
from datetime import datetime, timezone

import boto3
from sqlalchemy import select

from app.database import SessionLocal
from app.models.models import OutboxEvent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

QUEUE_URL = os.getenv("ORDER_QUEUE_URL")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

POLL_INTERVAL_SECONDS = 2
BATCH_SIZE = 10


def publish_pending_events():
    if not QUEUE_URL:
        raise RuntimeError(
            "ORDER_QUEUE_URL environment variable is required"
        )

    sqs = boto3.client(
        "sqs",
        region_name=AWS_REGION,
    )

    db = SessionLocal()

    try:
        events = db.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.processed.is_(False))
            .order_by(OutboxEvent.created_at)
            .limit(BATCH_SIZE)
        ).all()

        for event in events:
            try:
                sqs.send_message(
                    QueueUrl=QUEUE_URL,
                    MessageBody=event.payload,
                )

                event.processed = True
                event.processed_at = datetime.now(timezone.utc)

                db.commit()

                logger.info(
                    "outbox_event_published "
                    "event_id=%s "
                    "event_type=%s "
                    "aggregate_id=%s",
                    event.event_id,
                    event.event_type,
                    event.aggregate_id,
                )

            except Exception:
                db.rollback()

                logger.exception(
                    "outbox_event_publish_failed event_id=%s",
                    event.event_id,
                )

    finally:
        db.close()


def run_publisher():
    logger.info("outbox_publisher_started")

    while True:
        try:
            publish_pending_events()

        except Exception:
            logger.exception("outbox_publisher_cycle_failed")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_publisher()