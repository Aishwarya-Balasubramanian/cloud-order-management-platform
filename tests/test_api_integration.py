import os
import uuid

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app


# ---------------------------------------------------------
# Integration database configuration
#
# Local:
#   defaults to Docker PostgreSQL exposed on localhost:5433
#
# CI:
#   GitHub Actions supplies DB_HOST/DB_PORT/etc.
# ---------------------------------------------------------

TEST_DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "postgres"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5433")),
    database=os.getenv("DB_NAME", "order_management"),
)

test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def create_order_writer_token():
    secret = os.getenv(
        "JWT_SECRET",
        "local-development-secret-change-me-123456",
    )

    payload = {
        "sub": "integration-test-user",
        "role": "order_writer",
    }

    return jwt.encode(
        payload,
        secret,
        algorithm="HS256",
    )


def cleanup_test_data():
    """
    Remove records created by integration testing.
    """

    with test_engine.begin() as connection:
        connection.execute(
            text(
                """
                DELETE FROM processed_events;
                DELETE FROM outbox_events;
                DELETE FROM order_items;
                DELETE FROM orders;

                DELETE FROM products
                WHERE sku LIKE 'INT-%';

                DELETE FROM customers
                WHERE email LIKE 'integration-%@example.com';
                """
            )
        )


def test_real_order_flow_against_postgresql():
    """
    Exercise the real application path:

    HTTP
      -> FastAPI
      -> Pydantic
      -> JWT/RBAC
      -> service/repository
      -> SQLAlchemy
      -> PostgreSQL
    """

    cleanup_test_data()

    unique_id = uuid.uuid4().hex[:8]

    # -----------------------------------------------------
    # Create customer through HTTP API
    # -----------------------------------------------------

    customer_response = client.post(
        "/api/v1/customers",
        json={
            "name": "Integration Customer",
            "email": f"integration-{unique_id}@example.com",
        },
    )

    assert customer_response.status_code == 201

    customer = customer_response.json()

    assert customer["name"] == "Integration Customer"
    assert customer["active"] is True

    customer_id = customer["id"]

    # -----------------------------------------------------
    # Create product through HTTP API
    # -----------------------------------------------------

    product_response = client.post(
        "/api/v1/products",
        json={
            "sku": f"INT-{unique_id}",
            "name": "Integration Test Product",
            "price": "25.50",
        },
    )

    assert product_response.status_code == 201

    product = product_response.json()

    assert product["name"] == "Integration Test Product"

    product_id = product["id"]

    # -----------------------------------------------------
    # Create authenticated order
    # -----------------------------------------------------

    token = create_order_writer_token()

    order_response = client.post(
        "/api/v1/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-ID": f"integration-{unique_id}",
        },
        json={
            "customer_id": customer_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 2,
                }
            ],
        },
    )

    assert order_response.status_code == 201

    order = order_response.json()

    assert order["customer_id"] == customer_id
    assert order["status"] == "PENDING"
    assert float(order["total_amount"]) == 51.00

    assert len(order["items"]) == 1
    assert order["items"][0]["product_id"] == product_id
    assert order["items"][0]["quantity"] == 2

    order_id = order["id"]

    # -----------------------------------------------------
    # Read persisted order through HTTP API
    # -----------------------------------------------------

    get_response = client.get(
        f"/api/v1/orders/{order_id}"
    )

    assert get_response.status_code == 200

    persisted_order = get_response.json()

    assert persisted_order["id"] == order_id
    assert persisted_order["customer_id"] == customer_id
    assert persisted_order["status"] == "PENDING"
    assert float(persisted_order["total_amount"]) == 51.00

    # -----------------------------------------------------
    # Verify directly against PostgreSQL
    # -----------------------------------------------------

    with test_engine.connect() as connection:
        order_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE id = :order_id
                """
            ),
            {"order_id": order_id},
        ).scalar_one()

        outbox_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM outbox_events
                WHERE aggregate_id = :order_number
                """
            ),
            {
                "order_number": persisted_order[
                    "order_number"
                ]
            },
        ).scalar_one()

    assert order_count == 1
    assert outbox_count == 1

    cleanup_test_data()