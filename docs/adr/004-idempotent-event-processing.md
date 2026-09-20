# ADR 004: Idempotent Event Processing

## Status

Accepted

## Context

SQS uses at-least-once delivery. A message may therefore be delivered more than
once.

Repeated fulfillment could create duplicate downstream side effects.

## Decision

Persist processed event IDs in PostgreSQL.

Before processing an event, the worker checks whether its event ID has already
been recorded.

After successful fulfillment, the order state change and ProcessedEvent record
are committed together.

The fulfillment request also includes the order number as an idempotency key.

## Rationale

Persistent event tracking survives worker restarts and is stronger than
in-memory duplicate detection.

The downstream idempotency key provides an additional protection boundary.

## Important Limitation

There remains a failure window:

1. Fulfillment succeeds.
2. Worker crashes before committing ProcessedEvent.
3. SQS redelivers the event.

Therefore end-to-end duplicate protection requires the fulfillment service to
honor the idempotency key durably.

The system does not claim exactly-once processing.

## Consequences

Processed event records require storage and lifecycle management.

The design gains safer retry behavior and explicit duplicate-delivery handling.