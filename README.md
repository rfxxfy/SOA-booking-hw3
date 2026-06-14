# Flight Booking: gRPC + Redis

Распределённая система бронирования авиабилетов из двух микросервисов.

## Архитектура

```
Client (REST) → Booking Service → (gRPC) → Flight Service
                      ↓                          ↓
                 PostgreSQL               PostgreSQL + Redis Sentinel
```

## Запуск

Требуется Docker и Docker Compose (на macOS можно использовать [Colima](https://github.com/abiosoft/colima)).

```bash
docker-compose up --build
```

После старта:
- Booking Service REST API: http://localhost:8080
- Flight Service gRPC: localhost:50051

Миграции Flyway применяются автоматически при старте.

## Примеры запросов

```bash
# Поиск рейсов
curl "http://localhost:8080/flights?origin=SVO&destination=LED&date=2026-04-01"

# Получение рейса
curl "http://localhost:8080/flights/{flight_id}"

# Создание бронирования
curl -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user1",
    "flight_id": "{flight_id}",
    "passenger_name": "Ivan Ivanov",
    "passenger_email": "ivan@example.com",
    "seat_count": 2
  }'

# Получение бронирования
curl "http://localhost:8080/bookings/{booking_id}"

# Список бронирований пользователя
curl "http://localhost:8080/bookings?user_id=user1"

# Отмена бронирования
curl -X POST "http://localhost:8080/bookings/{booking_id}/cancel"
```

## Smoke test

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh
```

## Реализованные требования

### Блок 1-4
- gRPC-контракт Flight Service (`proto/flight.proto`) с кодогенерацией protoc
- ER-диаграмма в 3NF (`docs/er-diagram.md`)
- PostgreSQL + Flyway миграции для обоих сервисов
- REST API Booking Service и gRPC Flight Service
- Межсервисное взаимодействие по gRPC

### Блок 5-7
- Транзакции с `SELECT FOR UPDATE` в Flight Service
- API Key аутентификация gRPC через metadata (`x-api-key`)
- Redis Cache-Aside с TTL и инвалидацией при мутациях

### Блок 8-10
- Retry (3 попытки, exponential backoff) для UNAVAILABLE/DEADLINE_EXCEEDED
- Идемпотентность ReserveSeats по `booking_id`
- Redis Sentinel (master + replica + 3 sentinel)
- Circuit Breaker в Booking Service (конфиг через env)

## Переменные окружения

| Переменная | Сервис | Описание |
|---|---|---|
| `GRPC_API_KEY` | оба | API key для межсервисной аутентификации |
| `CACHE_TTL_SECONDS` | flight | TTL кеша (сек) |
| `GRPC_MAX_RETRIES` | booking | Макс. число retry |
| `CB_FAILURE_THRESHOLD` | booking | Порог ошибок CB |
| `CB_OPEN_TIMEOUT_SECONDS` | booking | Таймаут OPEN состояния |

## Структура проекта

```
proto/                  # gRPC контракт
docs/                   # ER-диаграмма
flight-service/         # gRPC сервис рейсов
booking-service/        # REST сервис бронирований
redis/                  # Sentinel конфигурация
scripts/                # Утилиты
docker-compose.yml
```
