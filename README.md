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
              │     PostgreSQL / RDS     │
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

The project focuses on engineering concerns that appear in production backend
and integration systems:

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
- automated application and infrastructure validation

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
- dead-letter queue
- transactional outbox
- persistent consumer idempotency
- REST/JSON fulfillment integration

### Cloud and Infrastructure

- AWS VPC
- Amazon RDS for PostgreSQL
- Amazon SQS
- Amazon ECR
- AWS IAM
- Amazon CloudWatch alarms
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

Order status updates require a `fulfillment_worker` or `admin` role.

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

The asynchronous fulfillment worker also protects against stale
`OrderCreated` events moving an order backwards in its lifecycle. Fulfillment
is only initiated for an order in the expected `PENDING` state.

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

inside the same PostgreSQL transaction.

A separate outbox publisher reads durable unpublished events and sends them to
SQS.

This prevents event intent from being lost if the API process fails after the
database transaction commits.

## Delivery Semantics and Idempotency

SQS is treated as an **at-least-once delivery system**.

The project deliberately does not claim exactly-once distributed processing.

Every `OrderCreated` event contains a unique `event_id`. The worker checks the
persistent `processed_events` table before executing fulfillment.

After successful fulfillment, the application persists:

```text
Order.status = CONFIRMED
        +
ProcessedEvent(event_id)
        +
PostgreSQL commit
```

The order-state change and processed-event marker therefore commit atomically
inside PostgreSQL.

The external fulfillment request also sends the order number as an
idempotency key.

This protects against common duplicate-delivery scenarios while acknowledging
an important distributed-systems boundary:

```text
Fulfillment succeeds
        ↓
worker crashes before PostgreSQL commit
        ↓
SQS redelivers event
        ↓
fulfillment may be called again
```

PostgreSQL and an external REST service cannot participate in the same local
database transaction. End-to-end duplicate protection therefore also requires
the downstream fulfillment service to honor the supplied idempotency key
durably.

A unique `event_id` constraint additionally protects the persistent
`ProcessedEvent` record from duplicate insertion.

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

Failed SQS messages are not acknowledged successfully and can therefore become
visible again for redelivery.

The Terraform SQS configuration defines a redrive policy so messages exceeding
the configured receive threshold can be routed to the DLQ.

Malformed, unsupported, or otherwise non-processable events are also left
unacknowledged so repeated failures can eventually be isolated in the DLQ for
investigation.

## Database Migrations

Database schema evolution is managed through Alembic.

Application startup does not create or mutate the production schema.

Typical workflow:

```text
SQLAlchemy model change
        ↓
Alembic revision
        ↓
Review migration
        ↓
Apply migration
        ↓
Regression tests
```

The repository contains migrations for the baseline order schema,
transactional outbox, and persistent processed-event tracking.

Docker Compose runs migrations before starting the API.

A Kubernetes migration Job is also provided as a deployment artifact.

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
application security group rather than exposing the database broadly.

The current JWT implementation uses HS256 for the portfolio/local runtime.

For a production identity architecture, this would typically be replaced by an
external identity provider using OIDC/JWKS and asymmetric token verification.

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

Executes a PostgreSQL connectivity check and returns HTTP `503` when the
database is unavailable.

Application logging includes:

- request ID
- HTTP method
- request path
- status code
- request duration
- worker failures
- outbox publication failures

Terraform defines CloudWatch alarms for:

- messages visible in the DLQ
- age of the oldest SQS message
- sustained high RDS CPU utilization

The alarm definitions are infrastructure artifacts and are not represented as
currently active in a live AWS environment.

## Testing

The automated test suite currently contains **13 passing tests** covering:

- customer/business validation
- server-authoritative pricing
- valid order lifecycle transitions
- invalid lifecycle transitions
- JWT validation
- fulfillment error classification
- transactional outbox creation
- duplicate event suppression
- successful processed-event recording
- retryable fulfillment failure behavior
- prevention of fulfillment from an invalid order state
- API/PostgreSQL integration behavior

The PostgreSQL integration test exercises:

```text
HTTP request
      ↓
FastAPI
      ↓
Pydantic validation
      ↓
JWT / RBAC
      ↓
Service / Repository
      ↓
SQLAlchemy
      ↓
PostgreSQL
```

It also verifies that order creation persists both the order and its
transactional outbox event.

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

FastAPI exposes interactive Swagger/OpenAPI documentation while the
application is running.

## Docker

The repository contains a Dockerfile and Docker Compose configuration.

Start the local application stack:

```powershell
docker compose up --build
```

The Compose startup sequence is:

```text
PostgreSQL
     ↓
health check
     ↓
Alembic migrations
     ↓
FastAPI
```

The Docker Compose development stack has been validated locally with:

- PostgreSQL 17
- Alembic migrations
- API startup
- `/health` liveness check
- `/ready` PostgreSQL readiness check
- PostgreSQL-backed API integration testing

The optional asynchronous profile starts the outbox publisher and order worker
when an SQS queue and fulfillment endpoint are configured:

```powershell
docker compose --profile async up
```

The asynchronous workers are not represented as having been exercised against
live AWS SQS in this portfolio environment.

## Kubernetes

The `k8s/` directory contains manifests for:

- API Deployment
- API Service
- order-worker Deployment
- outbox-publisher Deployment
- shared ConfigMap
- Alembic database migration Job

The API and worker are designed to scale independently.

The outbox publisher intentionally uses one replica because the current
implementation does not implement multi-publisher database row claiming.

For multiple publisher replicas, a future version should introduce safe
claiming semantics such as:

```sql
SELECT ... FOR UPDATE SKIP LOCKED
```

The Kubernetes files are deployment artifacts. They have **not** been deployed
to a live Kubernetes or EKS cluster in this portfolio environment.

## AWS / Terraform

Terraform definitions include:

- VPC
- private database subnets
- application and database security groups
- Amazon RDS for PostgreSQL
- SQS order queue
- SQS dead-letter queue
- Amazon ECR repository
- IAM policy
- CloudWatch alarms

RDS master credentials use AWS-managed password handling.

Terraform configuration is automatically formatted and validated in GitHub
Actions.

The infrastructure definitions are provided as reproducible architecture
artifacts. This repository does not claim that the AWS resources or an EKS
cluster are currently provisioned.

## CI

GitHub Actions validates the project on pushes and pull requests to `main`.

```text
Checkout
   ↓
Start PostgreSQL 17 service
   ↓
Python 3.13 setup
   ↓
Dependency installation
   ↓
Alembic migrations
   ↓
13-test automated suite
   ↓
Docker image build
   ↓
Terraform format check
   ↓
Terraform initialization
   ↓
Terraform validation
```

The pipeline has been executed successfully in GitHub Actions.

This provides independent validation of database migrations, application tests,
container image construction, and Terraform configuration outside the local
development environment.

Automatic production deployment is intentionally not enabled.

A production deployment would require an appropriately configured deployment
identity, such as GitHub OIDC, together with the target AWS runtime
infrastructure.

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

## Validation Status

Demonstrated locally and/or through GitHub Actions:

- FastAPI application startup
- PostgreSQL persistence
- Alembic schema migrations
- Docker image construction
- Docker Compose application/database startup
- liveness and readiness checks
- 13-test automated suite
- PostgreSQL-backed API integration test
- Terraform initialization and validation
- GitHub Actions CI execution

Implemented as architecture/deployment artifacts but not exercised against a
live cloud runtime:

- Amazon SQS / DLQ
- Amazon RDS
- Amazon ECR
- CloudWatch alarms
- Kubernetes deployments
- Kubernetes migration Job
- EKS deployment

This distinction is intentional: the repository separates implemented and
validated behavior from infrastructure that has been designed but not
provisioned.

## Known Limitations and Production Evolution

The project intentionally documents rather than hides its current boundaries.

Potential production evolution includes:

- OIDC/JWKS identity-provider integration
- structured JSON logging
- distributed tracing
- application-level metrics and dashboards
- notification routing for CloudWatch alarms
- multi-replica outbox publishing with safe row claiming
- retention/cleanup policies for processed events and outbox history
- full EKS cluster provisioning
- workload IAM integration such as IRSA
- AWS OIDC-based CI/CD deployment
- autoscaling policies
- rate limiting
- pagination and filtering for collection endpoints
- deeper database concurrency and load testing

These are explicit architectural evolution points rather than features
represented as already implemented.