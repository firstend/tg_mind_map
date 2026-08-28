"""Общее подключение к PostgreSQL."""

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from pgvector.psycopg2 import register_vector

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://mindmap:mindmap@localhost:5432/mindmap")


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
