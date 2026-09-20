# System Architecture

## Overview

Cloud Order Management Platform is a REST-based order-processing system designed
around transactional persistence, asynchronous fulfillment, failure isolation,
and cloud deployment.

## Runtime Architecture

```text
                         ┌──────────────────┐
                         │      Client      │
                         └────────┬─────────┘
                                  │ HTTPS / JSON
                                  ▼
                         ┌──────────────────┐
                         │ API Gateway / LB │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   FastAPI API    │
                         │ JWT / RBAC       │
                         └────────┬─────────┘
                                  │
                     Service / Repository
                                  │
                                  ▼
                    ┌────────────────────────┐
                    │    RDS PostgreSQL      │
                    │                        │
                    │ Orders                 │
                    │ OrderItems             │
                    │ OutboxEvents           │
                    │ ProcessedEvents        │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   Outbox Publisher     │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │       Amazon SQS       │
                    └───────────┬────────────┘
                                │
                    repeated failures ───────┼────→ DLQ
                                │
                                ▼
                    ┌────────────────────────┐
                    │     Order Worker       │
                    │ persistent idempotency │
                    └───────────┬────────────┘
                                │ HTTP / JSON
                                ▼
                    ┌────────────────────────┐
                    │   Fulfillment API      │
                    └────────────────────────┘