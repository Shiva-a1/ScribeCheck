import threading

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from shared import config

_pool = None
_lock = threading.Lock()


def connection():
    global _pool
    with _lock:
        if _pool is None:
            _pool = ConnectionPool(
                config.DATABASE_URL,
                min_size=1,
                max_size=10,
                kwargs={"row_factory": dict_row},
                configure=register_vector,
                open=True,
            )
    return _pool.connection()
