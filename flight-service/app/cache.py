import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

import redis
from redis.sentinel import Sentinel

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))


class FlightCache:
    def __init__(self) -> None:
        sentinel_hosts = os.getenv("REDIS_SENTINEL_HOSTS", "redis-sentinel:26379")
        master_name = os.getenv("REDIS_MASTER_NAME", "mymaster")
        password = os.getenv("REDIS_PASSWORD") or None

        hosts = []
        for entry in sentinel_hosts.split(","):
            host, port = entry.strip().split(":")
            hosts.append((host, int(port)))

        sentinel = Sentinel(
            hosts,
            socket_timeout=2.0,
            password=password,
            decode_responses=True,
        )
        self._client = sentinel.master_for(
            master_name,
            socket_timeout=2.0,
            password=password,
            decode_responses=True,
        )

    def get_flight(self, flight_id: str) -> dict[str, Any] | None:
        key = f"flight:{flight_id}"
        data = self._client.get(key)
        if data:
            logger.info("cache hit key=%s", key)
            return json.loads(data)
        logger.info("cache miss key=%s", key)
        return None

    def set_flight(self, flight: dict[str, Any]) -> None:
        key = f"flight:{flight['id']}"
        ttl = CACHE_TTL_SECONDS + random.randint(0, 60)
        self._client.setex(key, ttl, json.dumps(flight, default=str))
        logger.info("cache set key=%s ttl=%s", key, ttl)

    def get_search(self, origin: str, destination: str, date: str | None) -> list[dict[str, Any]] | None:
        date_key = date or "any"
        key = f"search:{origin}:{destination}:{date_key}"
        data = self._client.get(key)
        if data:
            logger.info("cache hit key=%s", key)
            return json.loads(data)
        logger.info("cache miss key=%s", key)
        return None

    def set_search(
        self,
        origin: str,
        destination: str,
        date: str | None,
        flights: list[dict[str, Any]],
    ) -> None:
        date_key = date or "any"
        key = f"search:{origin}:{destination}:{date_key}"
        ttl = CACHE_TTL_SECONDS + random.randint(0, 60)
        self._client.setex(key, ttl, json.dumps(flights, default=str))
        logger.info("cache set key=%s ttl=%s", key, ttl)

    def invalidate_flight(self, flight_id: str, origin: str, destination: str, departure_date: str) -> None:
        keys = [
            f"flight:{flight_id}",
            f"search:{origin}:{destination}:{departure_date}",
            f"search:{origin}:{destination}:any",
        ]
        deleted = self._client.delete(*keys)
        logger.info("cache invalidate flight_id=%s deleted=%s keys=%s", flight_id, deleted, keys)

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except redis.RedisError:
            return False
