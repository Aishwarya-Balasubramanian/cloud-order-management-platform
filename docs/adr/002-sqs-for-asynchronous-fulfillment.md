# ADR 002: SQS for Asynchronous Fulfillment

## Status

Accepted

## Context

Order creation should not depend directly on the availability or latency of an
external fulfillment system.

Calling fulfillment synchronously from the API would increase request latency
and couple order creation availability to an external dependency.

## Decision

Use Amazon SQS between order creation and fulfillment processing.

An independent worker consumes OrderCreated events and communicates with the
external fulfillment API.

A dead-letter queue captures messages that repeatedly fail processing.

## Rationale

SQS provides:

- Durable message buffering
- Loose coupling
- Independent producer and consumer scaling
- Retry through message redelivery
- Dead-letter queue support
- Managed AWS operation

## Alternatives Considered

### Synchronous HTTP

Simpler but tightly couples API availability and latency to fulfillment.

### Kafka

Kafka is appropriate when event streaming, replay, multiple consumer groups,
high throughput, or retained event history are core requirements.

Those requirements do not justify Kafka's additional operational complexity for
this system.

## Consequences

SQS provides at-least-once delivery, so consumers must tolerate duplicate
messages.

Worker processing therefore includes persistent idempotency handling.