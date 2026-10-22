# backend/common/db.py
"""Database helper that abstracts over SQLite and PostgreSQL back‑ends.
The backend is selected via the DB_BACKEND environment variable (default "sqlite").
When "postgres" is selected, the PostgreSQL helpers defined in backend.common.postgres
are re‑exported under the same names, so existing imports remain unchanged.
"""

import os
from contextlib import contextmanager

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()

# Placeholder for SQL parameter markers: '?' for SQLite, '%s' for PostgreSQL
PLACEHOLDER = "?" if DB_BACKEND == "sqlite" else "%s"

if DB_BACKEND == "postgres":
    # Re‑export PostgreSQL helpers
    from .postgres import init_db, get_connection, connection_context  # type: ignore
else:
    # SQLite implementation (unchanged logic)
    import sqlite3
    from typing import Generator

    DB_PATH = os.getenv("DB_PATH", "dev.db")

    def init_db() -> None:
        """Create tables if they don't exist and seed demo products. Idempotent."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS product (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
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
                cart_user_id TEXT,
                product_id TEXT,
                quantity INTEGER NOT NULL,
                PRIMARY KEY (cart_user_id, product_id),
                FOREIGN KEY (cart_user_id) REFERENCES cart(user_id),
                FOREIGN KEY (product_id) REFERENCES product(id)
            )
            """
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM product")
        count = cur.fetchone()[0]
        if count == 0:
            demo_products = [
                ("prod-1", "Widget A", "Simple widget", 9.99, 100),
                ("prod-2", "Gadget B", "Fancy gadget", 19.99, 50),
                ("prod-3", "Doohickey C", "Mysterious doohickey", 4.99, 200),
            ]
            cur.executemany(
                f"INSERT INTO product (id, name, description, price, inventory) VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER})",
                demo_products,
            )
            conn.commit()
        conn.close()

    def get_connection() -> sqlite3.Connection:
        return sqlite3.connect(DB_PATH)

    @contextmanager
    def connection_context() -> Generator[sqlite3.Connection, None, None]:
        conn = get_connection()
        try:
            yield conn
        finally:
            conn.close()
