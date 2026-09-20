from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.order_service import change_order_status


def test_valid_status_transition():
    db = MagicMock()

    order = MagicMock()
    order.status = "PENDING"

    with patch(
        "app.services.order_service.get_order_by_id",
        return_value=order
    ):
        result = change_order_status(
            db=db,
            order_id=1,
            new_status="CONFIRMED"
        )

    assert result.status == "CONFIRMED"
    db.commit.assert_called_once()


def test_invalid_status_transition():
    db = MagicMock()

    order = MagicMock()
    order.status = "COMPLETED"

    with patch(
        "app.services.order_service.get_order_by_id",
        return_value=order
    ):
        with pytest.raises(HTTPException) as exc:
            change_order_status(
                db=db,
                order_id=1,
                new_status="PENDING"
            )

    assert exc.value.status_code == 409