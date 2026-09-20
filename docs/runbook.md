
# Operational Runbook

## Purpose

This runbook describes initial investigation steps for common production-style
failure scenarios in the Cloud Order Management Platform.

---

## API Is Unavailable

### Check

- `/health`
- application process/container status
- recent application logs
- deployment replica availability

### Interpretation

If `/health` fails, the application process or container may be unhealthy.

If `/health` succeeds but `/ready` fails, investigate dependencies rather than
restarting the API blindly.

---

## API Is Alive but Not Ready

### Symptom

`/health` returns success but `/ready` returns HTTP 503.

### Likely Cause

PostgreSQL is unavailable or unreachable.

### Investigate

- RDS availability
- database connection configuration
- security groups
- credentials/secrets
- network connectivity
- database connection exhaustion

---

## Orders Are Created but Fulfillment Is Delayed

### Investigate

1. Check unprocessed `outbox_events`.
2. Check outbox publisher logs.
3. Check SQS queue depth.
4. Check `ApproximateAgeOfOldestMessage`.
5. Check worker replicas/logs.
6. Check external fulfillment availability.

### Interpretation

Unprocessed outbox rows suggest publisher problems.

Growing SQS age with a healthy publisher suggests worker capacity or worker
failure.

---

## Messages Appear in the DLQ

### Meaning

A message has repeatedly failed normal processing.

### Investigate

- worker logs
- event payload validity
- order existence/state
- external fulfillment response
- authentication/network failures
- retryable versus non-retryable error classification

Do not blindly redrive DLQ messages before understanding the failure. Replaying
a message can repeat downstream side effects if idempotency assumptions are
incorrect.

---

## Duplicate SQS Delivery

Duplicate delivery is expected under at-least-once messaging.

The worker checks `processed_events` using `event_id`.

If the event is already present, processing is skipped.

The fulfillment request also sends the order number as an idempotency key.

---

## Fulfillment API Timeout or 5xx

These failures are classified as retryable.

The worker does not delete the SQS message.

After the visibility timeout expires, SQS can deliver the message again.

Repeated failures eventually route the message to the DLQ according to the
configured redrive policy.

---

## Fulfillment Returns 4xx

Most 4xx responses are classified as non-retryable application failures.

Investigate request validity and downstream contract compatibility.

The current queue policy can still eventually move repeatedly received failed
messages to the DLQ for investigation.

---

## Outbox Publisher Failure

Order creation remains durable because the order and OutboxEvent were committed
together.

Restart/recover the publisher.

Unprocessed outbox rows remain available for later publication.

---

## Database CPU Alarm

### Investigate

- expensive queries
- missing/ineffective indexes
- connection volume
- lock contention
- workload spikes
- RDS sizing

Do not assume increasing instance size is the first solution. Determine whether
the pressure originates from query design, access patterns, concurrency, or
capacity.

---

## Schema Changes

Database schema changes must be performed through Alembic migrations.

Typical workflow:

```text
Modify SQLAlchemy model
        ↓
Generate Alembic revision
        ↓
Review migration
        ↓
Apply migration
        ↓
Run regression tests