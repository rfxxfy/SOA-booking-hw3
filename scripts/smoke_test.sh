#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"

echo "==> Health check"
curl -sf "$BASE_URL/health" | python3 -m json.tool

echo "==> Search flights SVO -> LED"
FLIGHTS=$(curl -sf "$BASE_URL/flights?origin=SVO&destination=LED&date=2026-04-01")
echo "$FLIGHTS" | python3 -m json.tool
FLIGHT_ID=$(echo "$FLIGHTS" | python3 -c "import sys, json; print(json.load(sys.stdin)['flights'][0]['id'])")
echo "Using flight_id=$FLIGHT_ID"

echo "==> Get flight"
curl -sf "$BASE_URL/flights/$FLIGHT_ID" | python3 -m json.tool

echo "==> Create booking"
BOOKING=$(curl -sf -X POST "$BASE_URL/bookings" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"user1\",\"flight_id\":\"$FLIGHT_ID\",\"passenger_name\":\"Ivan Ivanov\",\"passenger_email\":\"ivan@example.com\",\"seat_count\":2}")
echo "$BOOKING" | python3 -m json.tool
BOOKING_ID=$(echo "$BOOKING" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

echo "==> Get booking"
curl -sf "$BASE_URL/bookings/$BOOKING_ID" | python3 -m json.tool

echo "==> List bookings"
curl -sf "$BASE_URL/bookings?user_id=user1" | python3 -m json.tool

echo "==> Cancel booking"
curl -sf -X POST "$BASE_URL/bookings/$BOOKING_ID/cancel" | python3 -m json.tool

echo "All smoke tests passed"
