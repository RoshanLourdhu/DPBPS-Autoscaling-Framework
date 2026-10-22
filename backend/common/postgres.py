# backend/common/postgres.py
"""PostgreSQL DB helper for the platform.
Provides init_db, get_connection, and connection_context similar to the SQLite helper.
Environment variables:
  POSTGRES_HOST (default "postgres")
  POSTGRES_PORT (default "5432")
  POSTGRES_DB (default "dpbps")
  POSTGRES_USER (default "dpbps_user")
  POSTGRES_PASSWORD (default "dpbps_pass")
"""

import os
import pg8000

from contextlib import contextmanager
from typing import Generator

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "dpbps")
POSTGRES_USER = os.getenv("POSTGRES_USER", "dpbps_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "dpbps_pass")

_CONN_STR = f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"


def init_db() -> None:
    """Create tables if they do not exist and seed demo data (idempotent)."""
    with pg8000.connect(_CONN_STR) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS product (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price NUMERIC NOT NULL,
                inventory INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cart (
                user_id TEXT PRIMARY KEY
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cart_item (
                cart_user_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                PRIMARY KEY (cart_user_id, product_id),
                FOREIGN KEY (cart_user_id) REFERENCES cart(user_id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        # Seed demo products if table empty
        cur.execute("SELECT COUNT(*) FROM product")
        count = cur.fetchone()[0]
        if count == 0:
            demo_products = [
                ("prod-1", "Widget A", "Simple widget", 9.99, 100),
                ("prod-2", "Gadget B", "Fancy gadget", 19.99, 50),
                ("prod-3", "Doohickey C", "Mysterious doohickey", 4.99, 200),
            ]
            insert_sql = "INSERT INTO product (id, name, description, price, inventory) VALUES (%s, %s, %s, %s, %s)"
            cur.executemany(insert_sql, demo_products)
            conn.commit()


def get_connection():
    """Return a new PostgreSQL connection."""
    return pg8000.connect(_CONN_STR)


@contextmanager
def connection_context() -> Generator[pg8000.Connection, None, None]:
    """Yield a connection and ensure it is closed after use."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
