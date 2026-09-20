# ADR 001: PostgreSQL for Order Persistence

## Status

Accepted

## Context

The order-management platform requires durable storage for customers, products,
orders, and order items. The domain contains relational data, transactional
updates, uniqueness constraints, and lifecycle state changes.

## Decision

Use PostgreSQL as the system of record and SQLAlchemy as the application
persistence layer.

Database schema changes are versioned with Alembic rather than being created
implicitly during application startup.

## Rationale

PostgreSQL provides:

- ACID transactions
- Foreign-key constraints
- Unique constraints
- Relational joins
- Indexing
- Mature operational tooling
- Strong support through AWS RDS

The order domain benefits from relational integrity because an Order belongs to
a Customer and contains OrderItems referencing Products.

## Alternatives Considered

### DynamoDB

DynamoDB provides excellent horizontal scalability and managed availability,
but would require access-pattern-driven modeling and application-managed
relationships.

The current domain benefits more from relational consistency and transactions.

### In-memory persistence

Useful for prototypes and tests but unsuitable for durable order state.

## Consequences

The application depends on PostgreSQL availability for synchronous order
operations.

Database scaling, connection management, migrations, backups, and query
performance become operational concerns.

AWS deployment uses RDS PostgreSQL in private subnets.