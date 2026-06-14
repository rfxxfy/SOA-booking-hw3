import logging
import os
import time
from concurrent import futures

import grpc

from app.auth import AuthInterceptor
from app.cache import FlightCache
from app.db import wait_for_db
from app.service import FlightService
from generated import flight_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [flight-service] %(message)s",
)
logger = logging.getLogger(__name__)


def serve() -> None:
    wait_for_db()

    cache = FlightCache()
    for attempt in range(1, 31):
        if cache.ping():
            logger.info("redis is ready")
            break
        logger.warning("redis not ready attempt=%s", attempt)
        time.sleep(2)
    else:
        raise RuntimeError("redis is not available")

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=(AuthInterceptor(),),
        options=[("grpc.max_send_message_length", 10 * 1024 * 1024)],
    )
    flight_pb2_grpc.add_FlightServiceServicer_to_server(FlightService(cache), server)

    port = os.getenv("GRPC_PORT", "50051")
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("flight service started on port %s", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
