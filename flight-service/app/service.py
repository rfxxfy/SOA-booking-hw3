import logging
from datetime import datetime, timezone

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.cache import FlightCache
from app.db import db_cursor
from generated import flight_pb2, flight_pb2_grpc

logger = logging.getLogger(__name__)

STATUS_TO_PROTO = {
    "SCHEDULED": flight_pb2.SCHEDULED,
    "DEPARTED": flight_pb2.DEPARTED,
    "CANCELLED": flight_pb2.CANCELLED,
    "COMPLETED": flight_pb2.COMPLETED,
}

RESERVATION_STATUS_TO_PROTO = {
    "ACTIVE": flight_pb2.ACTIVE,
    "RELEASED": flight_pb2.RELEASED,
    "EXPIRED": flight_pb2.EXPIRED,
}


def _to_timestamp(dt: datetime | str) -> Timestamp:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    ts = Timestamp()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts.FromDatetime(dt)
    return ts


def _row_to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "flight_number": row["flight_number"],
        "airline": row["airline"],
        "origin": row["origin"],
        "destination": row["destination"],
        "departure_time": row["departure_time"],
        "arrival_time": row["arrival_time"],
        "total_seats": row["total_seats"],
        "available_seats": row["available_seats"],
        "price": row["price"],
        "status": row["status"],
        "departure_date": row["departure_date"].isoformat(),
    }


def _dict_to_proto(data: dict) -> flight_pb2.Flight:
    return flight_pb2.Flight(
        id=data["id"],
        flight_number=data["flight_number"],
        airline=data["airline"],
        origin=data["origin"],
        destination=data["destination"],
        departure_time=_to_timestamp(data["departure_time"]),
        arrival_time=_to_timestamp(data["arrival_time"]),
        total_seats=data["total_seats"],
        available_seats=data["available_seats"],
        price=data["price"],
        status=STATUS_TO_PROTO[data["status"]],
    )


class FlightService(flight_pb2_grpc.FlightServiceServicer):
    def __init__(self, cache: FlightCache) -> None:
        self.cache = cache

    def SearchFlights(self, request, context):
        if not request.origin or not request.destination:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("origin and destination are required")
            return flight_pb2.SearchFlightsResponse()

        date = request.date or None
        cached = self.cache.get_search(request.origin, request.destination, date)
        if cached is not None:
            return flight_pb2.SearchFlightsResponse(
                flights=[_dict_to_proto(item) for item in cached]
            )

        query = """
            SELECT *
            FROM flights
            WHERE origin = %s
              AND destination = %s
              AND status = 'SCHEDULED'
        """
        params: list = [request.origin, request.destination]
        if date:
            query += " AND departure_date = %s"
            params.append(date)
        query += " ORDER BY departure_time"

        with db_cursor() as cur:
            cur.execute(query, params)
            rows = [_row_to_dict(row) for row in cur.fetchall()]

        self.cache.set_search(request.origin, request.destination, date, rows)
        return flight_pb2.SearchFlightsResponse(flights=[_dict_to_proto(row) for row in rows])

    def GetFlight(self, request, context):
        if not request.id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("id is required")
            return flight_pb2.GetFlightResponse()

        cached = self.cache.get_flight(request.id)
        if cached is not None:
            return flight_pb2.GetFlightResponse(flight=_dict_to_proto(cached))

        with db_cursor() as cur:
            cur.execute("SELECT * FROM flights WHERE id = %s", (request.id,))
            row = cur.fetchone()

        if not row:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("flight not found")
            return flight_pb2.GetFlightResponse()

        data = _row_to_dict(row)
        self.cache.set_flight(data)
        return flight_pb2.GetFlightResponse(flight=_dict_to_proto(data))

    def ReserveSeats(self, request, context):
        if not request.flight_id or not request.booking_id or request.seat_count <= 0:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("flight_id, booking_id and positive seat_count are required")
            return flight_pb2.ReserveSeatsResponse()

        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT id, status, seat_count
                FROM seat_reservations
                WHERE booking_id = %s
                """,
                (request.booking_id,),
            )
            existing = cur.fetchone()
            if existing:
                if existing["status"] == "ACTIVE":
                    logger.info("idempotent reserve booking_id=%s", request.booking_id)
                    return flight_pb2.ReserveSeatsResponse(
                        reservation_id=str(existing["id"]),
                        status=RESERVATION_STATUS_TO_PROTO[existing["status"]],
                    )
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("reservation already exists and is not active")
                return flight_pb2.ReserveSeatsResponse()

            cur.execute(
                """
                SELECT id, available_seats, status, origin, destination, departure_date
                FROM flights
                WHERE id = %s
                FOR UPDATE
                """,
                (request.flight_id,),
            )
            flight = cur.fetchone()
            if not flight:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("flight not found")
                return flight_pb2.ReserveSeatsResponse()

            if flight["status"] != "SCHEDULED":
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("flight is not available for reservation")
                return flight_pb2.ReserveSeatsResponse()

            if flight["available_seats"] < request.seat_count:
                context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                context.set_details("insufficient seats")
                return flight_pb2.ReserveSeatsResponse()

            cur.execute(
                """
                UPDATE flights
                SET available_seats = available_seats - %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (request.seat_count, request.flight_id),
            )
            cur.execute(
                """
                INSERT INTO seat_reservations (flight_id, booking_id, seat_count, status)
                VALUES (%s, %s, %s, 'ACTIVE')
                RETURNING id, status
                """,
                (request.flight_id, request.booking_id, request.seat_count),
            )
            reservation = cur.fetchone()

        self.cache.invalidate_flight(
            request.flight_id,
            flight["origin"],
            flight["destination"],
            flight["departure_date"].isoformat(),
        )

        return flight_pb2.ReserveSeatsResponse(
            reservation_id=str(reservation["id"]),
            status=RESERVATION_STATUS_TO_PROTO[reservation["status"]],
        )

    def ReleaseReservation(self, request, context):
        if not request.booking_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("booking_id is required")
            return flight_pb2.ReleaseReservationResponse()

        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT sr.id, sr.seat_count, sr.status, f.id AS flight_id,
                       f.origin, f.destination, f.departure_date
                FROM seat_reservations sr
                JOIN flights f ON f.id = sr.flight_id
                WHERE sr.booking_id = %s
                FOR UPDATE OF sr, f
                """,
                (request.booking_id,),
            )
            reservation = cur.fetchone()

            if not reservation:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("reservation not found")
                return flight_pb2.ReleaseReservationResponse()

            if reservation["status"] == "RELEASED":
                logger.info("idempotent release booking_id=%s", request.booking_id)
                return flight_pb2.ReleaseReservationResponse(
                    status=RESERVATION_STATUS_TO_PROTO["RELEASED"]
                )

            if reservation["status"] != "ACTIVE":
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("reservation is not active")
                return flight_pb2.ReleaseReservationResponse()

            cur.execute(
                """
                UPDATE flights
                SET available_seats = available_seats + %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (reservation["seat_count"], reservation["flight_id"]),
            )
            cur.execute(
                """
                UPDATE seat_reservations
                SET status = 'RELEASED', updated_at = NOW()
                WHERE id = %s
                RETURNING status
                """,
                (reservation["id"],),
            )
            updated = cur.fetchone()

        self.cache.invalidate_flight(
            str(reservation["flight_id"]),
            reservation["origin"],
            reservation["destination"],
            reservation["departure_date"].isoformat(),
        )

        return flight_pb2.ReleaseReservationResponse(
            status=RESERVATION_STATUS_TO_PROTO[updated["status"]]
        )
