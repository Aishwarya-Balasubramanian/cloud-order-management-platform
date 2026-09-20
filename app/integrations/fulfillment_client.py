import httpx


class RetryableFulfillmentError(Exception):
    pass


class NonRetryableFulfillmentError(Exception):
    pass


class FulfillmentClient:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def create_fulfillment(self, order):
        payload = {
            "order_number": order.order_number,
            "customer_id": order.customer_id,
            "total_amount": str(order.total_amount)
        }

        headers = {
            "Idempotency-Key": order.order_number
        }

        try:
            response = httpx.post(
                f"{self.base_url}/fulfillments",
                json=payload,
                headers=headers,
                timeout=5.0
            )

        except (
            httpx.TimeoutException,
            httpx.ConnectError
        ) as exc:
            raise RetryableFulfillmentError(
                "Fulfillment service unavailable"
            ) from exc

        if response.status_code in {
            429,
            500,
            502,
            503,
            504
        }:
            raise RetryableFulfillmentError(
                f"Fulfillment service returned "
                f"{response.status_code}"
            )

        if 400 <= response.status_code < 500:
            raise NonRetryableFulfillmentError(
                f"Fulfillment request rejected with "
                f"{response.status_code}"
            )

        try:
            response.raise_for_status()
            return response.json()

        except ValueError as exc:
            raise NonRetryableFulfillmentError(
                "Fulfillment service returned invalid JSON"
            ) from exc