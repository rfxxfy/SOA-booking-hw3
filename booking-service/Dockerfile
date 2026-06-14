FROM python:3.11-slim

WORKDIR /app

COPY booking-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY proto /proto
RUN mkdir -p /app/generated && python -m grpc_tools.protoc \
    -I/proto \
    --python_out=/app/generated \
    --grpc_python_out=/app/generated \
    /proto/flight.proto \
    && sed -i 's/^import flight_pb2 as flight__pb2/from generated import flight_pb2 as flight__pb2/' /app/generated/flight_pb2_grpc.py \
    && touch /app/generated/__init__.py

COPY booking-service/app ./app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
