import logging
from typing import Optional

import grpc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from app.circuit_breaker import CircuitBreakerOpenError
from app.db import db_cursor
from app.grpc_client import FlightGrpcClient, flight_to_dict, new_booking_id
from generated import flight_pb2

logger = logging.getLogger(__name__)

router = APIRouter()

_flight_client: FlightGrpcClient | None = None


def set_flight_client(client: FlightGrpcClient) -> None:
    global _flight_client
    _flight_client = client


def get_flight_client() -> FlightGrpcClient:
    if _flight_client is None:
        raise RuntimeError("flight client is not initialized")
    return _flight_client


class CreateBookingRequest(BaseModel):
    user_id: str = Field(min_length=1)
    flight_id: str = Field(min_length=1)
    passenger_name: str = Field(min_length=1)
    passenger_email: EmailStr
    seat_count: int = Field(gt=0)


def _handle_grpc_error(exc: grpc.RpcError) -> HTTPException:
    code = exc.code()
    details = exc.details() or "grpc call failed"
    mapping = {
        grpc.StatusCode.NOT_FOUND: 404,
        grpc.StatusCode.RESOURCE_EXHAUSTED: 409,
        grpc.StatusCode.INVALID_ARGUMENT: 400,
        grpc.StatusCode.FAILED_PRECONDITION: 409,
        grpc.StatusCode.UNAUTHENTICATED: 502,
        grpc.StatusCode.UNAVAILABLE: 503,
        grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    }
    status_code = mapping.get(code, 502)
    return HTTPException(status_code=status_code, detail=details)


def _booking_row_to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "user_id": row["user_id"],
        "flight_id": str(row["flight_id"]),
        "passenger_name": row["passenger_name"],
        "passenger_email": row["passenger_email"],
        "seat_count": row["seat_count"],
        "total_price": row["total_price"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.get("/health")
def health(flight_client: FlightGrpcClient = Depends(get_flight_client)):
    return {"status": "ok", "circuit_breaker": flight_client.circuit_state}


@router.get("/flights")
def search_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: Optional[str] = Query(default=None),
    flight_client: FlightGrpcClient = Depends(get_flight_client),
):
    try:
        response = flight_client.search_flights(origin.upper(), destination.upper(), date)
        return {"flights": [flight_to_dict(f) for f in response.flights]}
    except CircuitBreakerOpenError:
        raise HTTPException(status_code=503, detail="flight service temporarily unavailable")
    except grpc.RpcError as exc:
        raise _handle_grpc_error(exc)


@router.get("/flights/{flight_id}")
def get_flight(
    flight_id: str,
    flight_client: FlightGrpcClient = Depends(get_flight_client),
):
    try:
        response = flight_client.get_flight(flight_id)
        return flight_to_dict(response.flight)
    except CircuitBreakerOpenError:
        raise HTTPException(status_code=503, detail="flight service temporarily unavailable")
    except grpc.RpcError as exc:
        raise _handle_grpc_error(exc)


@router.post("/bookings", status_code=201)
def create_booking(
    payload: CreateBookingRequest,
    flight_client: FlightGrpcClient = Depends(get_flight_client),
):
    booking_id = new_booking_id()

    try:
        flight_response = flight_client.get_flight(payload.flight_id)
        flight = flight_response.flight
        if flight.status != flight_pb2.SCHEDULED:
            raise HTTPException(status_code=409, detail="flight is not available for booking")

        flight_client.reserve_seats(payload.flight_id, payload.seat_count, booking_id)
        total_price = payload.seat_count * flight.price

        try:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO bookings (
                        id, user_id, flight_id, passenger_name, passenger_email,
                        seat_count, total_price, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'CONFIRMED')
                    RETURNING *
                    """,
                    (
                        booking_id,
                        payload.user_id,
                        payload.flight_id,
                        payload.passenger_name,
                        payload.passenger_email,
                        payload.seat_count,
                        total_price,
                    ),
                )
                row = cur.fetchone()
        except Exception:
            try:
                flight_client.release_reservation(booking_id)
            except Exception:
                logger.exception("failed to release reservation after booking insert error")
            raise

        return _booking_row_to_dict(row)
    except CircuitBreakerOpenError:
        raise HTTPException(status_code=503, detail="flight service temporarily unavailable")
    except grpc.RpcError as exc:
        raise _handle_grpc_error(exc)


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="booking not found")
    return _booking_row_to_dict(row)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: str,
    flight_client: FlightGrpcClient = Depends(get_flight_client),
):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="booking not found")
    if row["status"] != "CONFIRMED":
        raise HTTPException(status_code=409, detail="booking is not confirmed")

    try:
        flight_client.release_reservation(booking_id)
    except CircuitBreakerOpenError:
        raise HTTPException(status_code=503, detail="flight service temporarily unavailable")
    except grpc.RpcError as exc:
        if exc.code() != grpc.StatusCode.NOT_FOUND:
            raise _handle_grpc_error(exc)

    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE bookings
            SET status = 'CANCELLED', updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (booking_id,),
        )
        updated = cur.fetchone()

    return _booking_row_to_dict(updated)


@router.get("/bookings")
def list_bookings(user_id: str = Query(..., min_length=1)):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM bookings
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    return {"bookings": [_booking_row_to_dict(row) for row in rows]}
