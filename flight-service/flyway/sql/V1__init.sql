CREATE TABLE flights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_number VARCHAR(20) NOT NULL,
    departure_date DATE NOT NULL,
    airline VARCHAR(100) NOT NULL,
    origin VARCHAR(3) NOT NULL,
    destination VARCHAR(3) NOT NULL,
    departure_time TIMESTAMPTZ NOT NULL,
    arrival_time TIMESTAMPTZ NOT NULL,
    total_seats INT NOT NULL CHECK (total_seats > 0),
    available_seats INT NOT NULL CHECK (available_seats >= 0),
    price BIGINT NOT NULL CHECK (price > 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('SCHEDULED', 'DEPARTED', 'CANCELLED', 'COMPLETED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT available_le_total CHECK (available_seats <= total_seats),
    CONSTRAINT unique_flight_number_date UNIQUE (flight_number, departure_date)
);

CREATE TABLE seat_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_id UUID NOT NULL REFERENCES flights(id),
    booking_id UUID NOT NULL UNIQUE,
    seat_count INT NOT NULL CHECK (seat_count > 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED', 'EXPIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_flights_route_date ON flights(origin, destination, departure_date);
CREATE INDEX idx_flights_status ON flights(status);
CREATE INDEX idx_reservations_flight ON seat_reservations(flight_id);
CREATE INDEX idx_reservations_status ON seat_reservations(status);

-- Seed data
INSERT INTO flights (flight_number, departure_date, airline, origin, destination, departure_time, arrival_time, total_seats, available_seats, price, status)
VALUES
    ('SU1234', '2026-04-01', 'Aeroflot', 'SVO', 'LED', '2026-04-01 08:00:00+03', '2026-04-01 09:30:00+03', 180, 180, 5000, 'SCHEDULED'),
    ('SU5678', '2026-04-01', 'Aeroflot', 'SVO', 'LED', '2026-04-01 14:00:00+03', '2026-04-01 15:30:00+03', 150, 150, 4500, 'SCHEDULED'),
    ('DP9012', '2026-04-01', 'Pobeda', 'VKO', 'LED', '2026-04-01 10:00:00+03', '2026-04-01 11:30:00+03', 120, 120, 3500, 'SCHEDULED'),
    ('SU1234', '2026-04-02', 'Aeroflot', 'SVO', 'LED', '2026-04-02 08:00:00+03', '2026-04-02 09:30:00+03', 180, 180, 5500, 'SCHEDULED'),
    ('S71001', '2026-04-01', 'S7 Airlines', 'DME', 'LED', '2026-04-01 16:00:00+03', '2026-04-01 17:30:00+03', 100, 100, 4000, 'SCHEDULED');
