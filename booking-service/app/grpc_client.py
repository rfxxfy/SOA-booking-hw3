import logging
import os
import uuid

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, create_circuit_breaker
from app.retry import call_with_retry
from generated import flight_pb2, flight_pb2_grpc

logger = logging.getLogger(__name__)

API_KEY_HEADER = "x-api-key"


class FlightGrpcClient:
    def __init__(self, circuit_breaker: CircuitBreaker | None = None) -> None:
        target = os.getenv("FLIGHT_SERVICE_HOST", "flight-service:50051")
        self._api_key = os.getenv("GRPC_API_KEY", "dev-api-key")
        self._channel = grpc.insecure_channel(target)
        self._stub = flight_pb2_grpc.FlightServiceStub(self._channel)
        self._circuit_breaker = circuit_breaker or create_circuit_breaker()

    def _metadata(self) -> list[tuple[str, str]]:
        return [(API_KEY_HEADER, self._api_key)]

    def _invoke(self, fn):
        self._circuit_breaker.before_call()
        try:
            result = call_with_retry(fn)
            self._circuit_breaker.on_success()
            return result
        except Exception:
            self._circuit_breaker.on_failure()
            raise

    def search_flights(self, origin: str, destination: str, date: str | None = None):
        request = flight_pb2.SearchFlightsRequest(
            origin=origin,
            destination=destination,
            date=date or "",
        )
        return self._invoke(
            lambda: self._stub.SearchFlights(request, metadata=self._metadata())
        )

    def get_flight(self, flight_id: str):
        request = flight_pb2.GetFlightRequest(id=flight_id)
        return self._invoke(
            lambda: self._stub.GetFlight(request, metadata=self._metadata())
        )

    def reserve_seats(self, flight_id: str, seat_count: int, booking_id: str):
        request = flight_pb2.ReserveSeatsRequest(
            flight_id=flight_id,
            seat_count=seat_count,
            booking_id=booking_id,
        )
        return self._invoke(
            lambda: self._stub.ReserveSeats(request, metadata=self._metadata())
        )

    def release_reservation(self, booking_id: str):
        request = flight_pb2.ReleaseReservationRequest(booking_id=booking_id)
        return self._invoke(
            lambda: self._stub.ReleaseReservation(request, metadata=self._metadata())
        )

    @property
    def circuit_state(self) -> str:
        return self._circuit_breaker.state.value


def proto_timestamp_to_iso(ts: Timestamp) -> str:
    return ts.ToDatetime().isoformat()


def flight_to_dict(flight: flight_pb2.Flight) -> dict:
    status_name = flight_pb2.FlightStatus.Name(flight.status)
    return {
        "id": flight.id,
        "flight_number": flight.flight_number,
        "airline": flight.airline,
        "origin": flight.origin,
        "destination": flight.destination,
        "departure_time": proto_timestamp_to_iso(flight.departure_time),
        "arrival_time": proto_timestamp_to_iso(flight.arrival_time),
        "total_seats": flight.total_seats,
        "available_seats": flight.available_seats,
        "price": flight.price,
        "status": status_name,
    }


def new_booking_id() -> str:
    return str(uuid.uuid4())
