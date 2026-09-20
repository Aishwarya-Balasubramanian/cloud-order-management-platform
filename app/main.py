import logging
import time
import uuid

from fastapi import FastAPI, Request, Response, status
from sqlalchemy import text

from app.api.customers import router as customers_router
from app.api.products import router as products_router
from app.api.orders import router as orders_router
from app.database import engine


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


app = FastAPI(
    title="Cloud Order Management Platform",
    description=(
        "Order management API with PostgreSQL, "
        "asynchronous order processing, "
        "and external fulfillment integration."
    ),
    version="1.0.0",
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get(
        "X-Request-ID",
        str(uuid.uuid4()),
    )

    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "request_completed "
        "request_id=%s "
        "method=%s "
        "path=%s "
        "status=%s "
        "duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    return response


@app.get("/health")
def health_check():
    """Liveness: is the application process alive?"""
    return {
        "status": "healthy",
        "service": "order-management-api",
    }


@app.get("/ready")
def readiness_check(response: Response):
    """Readiness: can this instance reach PostgreSQL?"""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ready",
            "database": "reachable",
        }

    except Exception:
        logger.exception("readiness_check_failed")

        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "not_ready",
            "database": "unreachable",
        }


app.include_router(customers_router)
app.include_router(products_router)
app.include_router(orders_router)