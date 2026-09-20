# ADR 003: Transactional Outbox

## Status

Accepted

## Context

Persisting an order and publishing an SQS event are two independent operations.

A naive implementation can produce this failure:

1. PostgreSQL commits the order.
2. The application crashes before publishing to SQS.
3. The order exists but fulfillment never begins.

Publishing first creates the inverse problem: an event may exist for an order
whose database transaction later fails.

## Decision

Use the transactional outbox pattern.

Order data and an OutboxEvent are persisted in the same PostgreSQL transaction.

A separate outbox publisher reads unpublished events, publishes them to SQS,
and marks them as processed.

## Rationale

The database transaction guarantees that either both the order and event intent
are persisted or neither is persisted.

This removes the database/SQS dual-write gap from the API request.

## Delivery Semantics

The publisher can successfully publish to SQS and fail before marking the
outbox row processed.

The event can therefore be published again.

The design intentionally assumes at-least-once delivery rather than claiming
exactly-once delivery.

Consumers must be idempotent.

## Current Limitation

The current publisher runs as one replica.

A horizontally scaled publisher should introduce safe event claiming, for
example database row locking with `FOR UPDATE SKIP LOCKED`, or another
coordination mechanism.

## Consequences

The architecture gains an additional background process and outbox table.

In return, order creation no longer depends directly on SQS availability.