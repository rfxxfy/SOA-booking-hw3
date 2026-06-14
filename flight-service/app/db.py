import logging
import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "flight-db"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "flights"),
        user=os.getenv("DB_USER", "flight"),
        password=os.getenv("DB_PASSWORD", "flight"),
    )


@contextmanager
def db_cursor(*, commit: bool = False):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    import time

    for attempt in range(1, retries + 1):
        try:
            with db_cursor() as cur:
                cur.execute("SELECT 1")
            logger.info("database is ready")
            return
        except psycopg2.OperationalError as exc:
            logger.warning("database not ready attempt=%s error=%s", attempt, exc)
            time.sleep(delay)
    raise RuntimeError("database is not available")
