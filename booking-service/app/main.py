import logging

from fastapi import FastAPI

from app.api import router, set_flight_client
from app.db import wait_for_db
from app.grpc_client import FlightGrpcClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [booking-service] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Booking Service", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    wait_for_db()
    set_flight_client(FlightGrpcClient())
    logger.info("booking service started")


app.include_router(router)
