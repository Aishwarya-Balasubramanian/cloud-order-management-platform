from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.auth import require_roles

from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate
)

from app.repositories.order_repository import (
    get_all_orders,
    get_order_by_id
)

from app.services.order_service import (
    create_order as create_order_service,
    change_order_status
)


router = APIRouter(
    prefix="/api/v1/orders",
    tags=["Orders"]
)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=201
)
def create_order(
    order: OrderCreate,
    db: Session = Depends(get_db),
    user=Depends(
        require_roles(
            "order_writer",
            "admin"
        )
    )
):
    return create_order_service(
        db,
        order
    )


@router.get(
    "",
    response_model=list[OrderResponse]
)
def get_orders(
    db: Session = Depends(get_db)
):
    return get_all_orders(db)


@router.get(
    "/{order_id}",
    response_model=OrderResponse
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    order = get_order_by_id(
        db,
        order_id
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    return order


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse
)
def update_order_status(
    order_id: int,
    update: OrderStatusUpdate,
    db: Session = Depends(get_db),
    user=Depends(
        require_roles(
            "fulfillment_worker",
            "admin"
        )
    )
):
    return change_order_status(
        db=db,
        order_id=order_id,
        new_status=update.status.value
    )