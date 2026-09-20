# Cloud Order Management Platform

A production-oriented order-management backend demonstrating REST API design,
transactional persistence, asynchronous event processing, idempotent consumers,
external service integration, AWS infrastructure design, containerization, and
operational failure handling.

The project is intentionally designed around a realistic order-processing
workflow rather than a CRUD-only API.

## Architecture

```text
                            Client
                              │
                         HTTPS / JSON
                              │
                              ▼
                     API Gateway / Load Balancer
                              │
                              ▼
                     ┌──────────────────┐
                     │     FastAPI      │
                     │    JWT / RBAC    │
                     └────────┬─────────┘
                              │
                    Service / Repository
                              │
                              ▼
                 ┌──────────────────────────┐
                 │      PostgreSQL / RDS    │
                 │                          │
                 │ Orders + OrderItems      │
                 │ OutboxEvents             │
                 │ ProcessedEvents          │
                 └────────────┬─────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Outbox Publisher │
                    └────────┬─────────┘
                             │
                             ▼
                        Amazon SQS
                         │       │
                         │       └────────→ DLQ
                         ▼
                    Order Worker
                         │
                    HTTP / JSON
                         │
                         ▼
                   Fulfillment API
```

## Engineering Goals

The project focuses on several problems that appear in production backend and
integration systems:

- API contract validation
- business-rule enforcement
- transactional persistence
- database schema evolution
- asynchronous processing
- database/message-broker consistency
- duplicate message delivery
- external dependency failures
- authentication and authorization
- infrastructure isolation
- observability and operational troubleshooting

## Technology Stack

### Application

- Python 3.13
- FastAPI
- Pydantic
- SQLAlchemy
- PostgreSQL
- Alembic
- HTTPX
- PyJWT

### Messaging and Integration

- Amazon SQS
- Dead-letter queue
- Transactional outbox
- Persistent consumer idempotency
- REST/JSON fulfillment integration

### Cloud and Infrastructure

- AWS VPC
- Amazon RDS for PostgreSQL
- Amazon SQS
- Amazon ECR
- AWS IAM
- CloudWatch alarms
- Terraform

### Runtime and Delivery

- Docker
- Docker Compose
- Kubernetes deployment manifests
- GitHub Actions CI
- pytest

## Domain Model

```text
Customer
   │
   └────< Order
            │
            └────< OrderItem >──── Product

Order creation
   │
   └──── OutboxEvent

SQS processing
   │
   └──── ProcessedEvent
```

Orders maintain a snapshot of product SKU and unit price so historical order
values do not change when the product catalog changes.

## API

### Customers

```text
POST /api/v1/customers
GET  /api/v1/customers/{customer_id}
```

### Products

```text
POST /api/v1/products
GET  /api/v1/products
GET  /api/v1/products/{product_id}
```

### Orders

```text
POST  /api/v1/orders
GET   /api/v1/orders
GET   /api/v1/orders/{order_id}
PATCH /api/v1/orders/{order_id}/status
```

Order creation requires an authorized `order_writer` or `admin` role.

Order status updates require `fulfillment_worker` or `admin`.

## Order Lifecycle

```text
PENDING
   ├────→ CANCELLED
   │
   └────→ CONFIRMED
              ├────→ CANCELLED
              │
              └────→ PROCESSING
                         │
                         ▼
                       SHIPPED
                         │
                         ▼
                      COMPLETED
```

Invalid state transitions return HTTP `409 Conflict`.

## Transactional Outbox

A direct implementation such as:

```text
COMMIT order
     ↓
publish SQS event
```

creates a dual-write failure window. PostgreSQL may commit successfully while
event publication fails.

This project instead persists:

```text
Order
OrderItems
OutboxEvent
```

inside the same database transaction.

A separate publisher sends durable outbox events to SQS.

This ensures that event intent is not lost when the API process fails after the
database commit.

## Delivery Semantics and Idempotency

SQS is treated as an at-least-once delivery system.

The project deliberately does not claim exactly-once distributed processing.

Every order-created event contains a unique `event_id`.

The worker checks the persistent `processed_events` table before executing
fulfillment.

After successful fulfillment:

```text
Order.status = CONFIRMED
+
ProcessedEvent(event_id)
+
database commit
```

The external fulfillment request also sends the order number as an idempotency
key.

This protects against common duplicate-delivery scenarios while acknowledging
that end-to-end idempotency also requires the downstream service to honor the
idempotency key.

## Failure Handling

External fulfillment failures are classified into retryable and non-retryable
categories.

Retryable examples include:

- connection failures
- timeouts
- HTTP 429
- HTTP 500
- HTTP 502
- HTTP 503
- HTTP 504

Failed SQS messages are not acknowledged successfully and can be redelivered.

Messages exceeding the configured receive threshold are routed to the DLQ.

## Database Migrations

Database schema evolution is managed through Alembic.

Application startup does not create or mutate the production schema.

Typical workflow:

```text
SQLAlchemy model change
        ↓
Alembic revision
        ↓
Review generated migration
        ↓
Apply migration
        ↓
Regression tests
```

## Security

Implemented application controls include:

- JWT authentication
- role-based authorization
- secrets excluded from Git
- environment-based runtime configuration
- Kubernetes Secret references
- IAM policy definitions
- private RDS networking
- security-group isolation

The Terraform database security group accepts PostgreSQL traffic from the
application security group rather than the entire VPC.

For a production identity system, the shared-secret JWT implementation would
typically be replaced by an external identity provider using OIDC/JWKS and
asymmetric token verification.

## Health and Observability

### Liveness

```text
GET /health
```

Confirms that the application process is alive.

### Readiness

```text
GET /ready
```

Executes a PostgreSQL connectivity check and returns HTTP 503 when the database
is unavailable.

Application logging includes:

- request ID
- HTTP method
- request path
- status code
- request duration
- worker failures
- outbox publication failures

Terraform also defines alarms for:

- messages visible in the DLQ
- age of the oldest SQS message
- sustained high RDS CPU utilization

## Testing

The automated test suite covers:

- customer validation
- server-authoritative pricing
- valid order lifecycle transitions
- invalid lifecycle transitions
- JWT validation
- fulfillment error classification
- transactional outbox creation
- duplicate event suppression
- successful processed-event recording
- retryable fulfillment failure behavior

Run:

```powershell
python -m pytest -v
```

## Local Development

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create local configuration:

```text
Copy .env.example to .env
and provide local values.
```

Apply database migrations:

```powershell
alembic upgrade head
```

Run the API:

```powershell
python -m uvicorn app.main:app --reload
```

Swagger/OpenAPI documentation is available through FastAPI while the application
is running.

## Docker

The repository contains a Dockerfile and Docker Compose configuration.

Basic local stack:

```powershell
docker compose up
```

The optional asynchronous profile starts the outbox publisher and order worker
when an SQS queue is configured:

```powershell
docker compose --profile async up
```

Docker execution has not been validated in every development environment and
requires Docker Engine/Desktop to be installed.

## Kubernetes

The `k8s/` directory contains manifests for:

- API deployment
- API service
- order worker
- outbox publisher
- shared configuration

The API and worker can scale independently.

The outbox publisher intentionally uses one replica because the current
implementation does not yet implement multi-publisher database row claiming.

For multiple publisher replicas, a future version should introduce safe
claiming semantics such as `SELECT ... FOR UPDATE SKIP LOCKED`.

## AWS / Terraform

Terraform definitions include:

- VPC
- private database subnets
- application and database security groups
- RDS PostgreSQL
- SQS order queue
- dead-letter queue
- ECR repository
- IAM policy
- CloudWatch alarms

RDS master credentials use AWS-managed password handling.

The infrastructure definitions are provided as reproducible architecture
artifacts. This repository does not claim that all AWS resources or an EKS
cluster are currently deployed.

## CI

GitHub Actions performs:

```text
Checkout
   ↓
Python setup
   ↓
Dependency installation
   ↓
pytest
   ↓
Docker image build
```

Automatic production deployment is intentionally not enabled without an AWS
OIDC/deployment configuration.

## Architecture Decisions

Detailed design decisions are documented under `docs/adr/`:

- PostgreSQL for transactional order persistence
- SQS for asynchronous fulfillment
- transactional outbox for database/message consistency
- persistent idempotency for at-least-once event processing

## Operations

See:

```text
docs/runbook.md
```

for investigation procedures covering:

- API availability
- database readiness failures
- fulfillment delays
- DLQ messages
- duplicate delivery
- external API failures
- outbox publisher failures
- database pressure
- schema changes
- secret exposure

## Known Limitations and Production Evolution

The project intentionally documents rather than hides its current boundaries.

Potential production evolution includes:

- OIDC/JWKS identity provider integration
- structured JSON logging
- distributed tracing
- application-level metrics and dashboards
- notification routing for CloudWatch alarms
- PostgreSQL integration/contract tests in CI
- multi-replica outbox publisher with safe row claiming
- retention/cleanup policies for processed events and outbox history
- full EKS cluster provisioning
- AWS OIDC-based CI/CD deployment
- autoscaling policies
- rate limiting
- pagination/filtering for collection endpoints

These are treated as explicit architectural evolution points rather than
features that are falsely represented as already implemented.