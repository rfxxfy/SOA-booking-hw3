# ER Diagram (3NF)

## Flight Service Database

```mermaid
erDiagram
    flights {
        uuid id PK
        varchar flight_number "NOT NULL"
        date departure_date "NOT NULL"
        varchar airline "NOT NULL"
        varchar origin "NOT NULL, IATA 3 chars"
        varchar destination "NOT NULL, IATA 3 chars"
        timestamptz departure_time "NOT NULL"
        timestamptz arrival_time "NOT NULL"
        int total_seats "NOT NULL, CHECK > 0"
        int available_seats "NOT NULL, CHECK >= 0"
        bigint price "NOT NULL, CHECK > 0"
        varchar status "NOT NULL, SCHEDULED|DEPARTED|CANCELLED|COMPLETED"
        timestamptz created_at
        timestamptz updated_at
    }

    seat_reservations {
        uuid id PK
        uuid flight_id FK "NOT NULL"
        uuid booking_id "NOT NULL, UNIQUE"
        int seat_count "NOT NULL, CHECK > 0"
        varchar status "NOT NULL, ACTIVE|RELEASED|EXPIRED"
        timestamptz created_at
        timestamptz updated_at
    }

    flights ||--o{ seat_reservations : "has"
```

**Constraints:**
- `UNIQUE(flight_number, departure_date)` — one flight per number per day
- `available_seats <= total_seats`
- One `booking_id` maps to exactly one reservation (`UNIQUE(booking_id)`)

## Booking Service Database

```mermaid
erDiagram
    bookings {
        uuid id PK
        varchar user_id "NOT NULL"
        uuid flight_id "NOT NULL"
        varchar passenger_name "NOT NULL"
        varchar passenger_email "NOT NULL"
        int seat_count "NOT NULL, CHECK > 0"
        bigint total_price "NOT NULL, CHECK > 0"
        varchar status "NOT NULL, CONFIRMED|CANCELLED"
        timestamptz created_at
        timestamptz updated_at
    }
```

**Notes:**
- `flight_id` references Flight Service logically (no cross-DB FK)
- `total_price` is a snapshot at booking time (`seat_count * flight.price`)
