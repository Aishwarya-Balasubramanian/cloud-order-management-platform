from unittest.mock import patch

import httpx
import pytest

from app.integrations.fulfillment_client import (
    FulfillmentClient,
    NonRetryableFulfillmentError,
    RetryableFulfillmentError
)


class FakeOrder:
    order_number = "ORD-TEST-001"
    customer_id = 1
    total_amount = 100


def test_fulfillment_timeout_is_retryable():
    client = FulfillmentClient(
        "http://fulfillment.example"
    )

    with patch(
        "app.integrations.fulfillment_client.httpx.post",
        side_effect=httpx.TimeoutException("timeout")
    ):
        with pytest.raises(
            RetryableFulfillmentError
        ):
            client.create_fulfillment(
                FakeOrder()
            )


def test_fulfillment_400_is_not_retryable():
    client = FulfillmentClient(
        "http://fulfillment.example"
    )

    response = httpx.Response(
        status_code=400
    )

    with patch(
        "app.integrations.fulfillment_client.httpx.post",
        return_value=response
    ):
        with pytest.raises(
            NonRetryableFulfillmentError
        ):
            client.create_fulfillment(
                FakeOrder()
            )