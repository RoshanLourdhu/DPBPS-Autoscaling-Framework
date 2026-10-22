# backend/tests/test_postgres.py
"""Automated tests for the database abstraction layer.

The tests cover both SQLite (default) and PostgreSQL back‑ends.  When a
PostgreSQL server is reachable the PostgreSQL tests are executed; otherwise
they are reported as *skipped*.
"""

import os
import tempfile
import pytest

# ---------------------------------------------------------------------------
# Helper to (re)load the db module after changing environment variables.
# ---------------------------------------------------------------------------
def load_db_module(backend: str):
    """Set ``DB_BACKEND`` and import/reload the ``backend.common.db`` module.

    The function returns the imported module so the caller can use the API
    directly (``init_db``, ``connection_context`` and ``PLACEHOLDER``).
    """
    os.environ["DB_BACKEND"] = backend
    # When switching back‑ends we must ensure the module is re‑executed.
    import importlib, sys
    if "backend.common.db" in sys.modules:
        del sys.modules["backend.common.db"]
    return importlib.import_module("backend.common.db")

# ---------------------------------------------------------------------------
# SQLite tests – always run using a temporary file.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def sqlite_db():
    """Create an isolated SQLite database for a single test.

    The fixture sets ``DB_PATH`` to a temporary file, loads the db module with
    ``DB_BACKEND=sqlite`` and yields the module.  After the test the temporary
    file is removed.
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        path = tmp.name
    os.environ["DB_PATH"] = path
    db = load_db_module("sqlite")
    # Ensure a clean start – ``init_db`` creates tables and seeds demo data.
    db.init_db()
    yield db
    # Clean up the temporary SQLite file.
    try:
        os.remove(path)
    except OSError:
        pass

def test_sqlite_initialisation(sqlite_db):
    """Verify that the schema is created and demo data is present."""
    db = sqlite_db
    with db.connection_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM product")
        count = cur.fetchone()[0]
        assert count > 0

def test_sqlite_crud(sqlite_db):
    db = sqlite_db
    # Insert a new product using the backend‑aware placeholder.
    with db.connection_context() as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO product (id, name, description, price, inventory) VALUES ({db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER})",
            ("test-xyz", "Test Product", "Demo", 12.34, 5),
        )
        conn.commit()

        # Read it back.
        cur.execute(
            f"SELECT name, price, inventory FROM product WHERE id = {db.PLACEHOLDER}",
            ("test-xyz",),
        )
        row = cur.fetchone()
        assert row == ("Test Product", 12.34, 5)

    # Verify rollback on error.
    with pytest.raises(RuntimeError):
        with db.connection_context() as conn:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO product (id, name, description, price, inventory) VALUES ({db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER})",
                ("rollback-id", "Tmp", "Tmp", 1.0, 1),
            )
            raise RuntimeError("force rollback")
    # Ensure the row was not persisted.
    with db.connection_context() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM product WHERE id = {db.PLACEHOLDER}", ("rollback-id",))
        assert cur.fetchone() is None

# ---------------------------------------------------------------------------
# PostgreSQL tests – skip if a server cannot be reached.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def postgres_available():
    """Attempt a lightweight connection to PostgreSQL.

    The fixture returns ``True`` when a connection can be opened using the
    default environment variables (``POSTGRES_*``).  If the connection fails the
    tests that depend on it are automatically skipped.
    """
    try:
        import pg8000
        conn_str = (
            f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
            f"port={os.getenv('POSTGRES_PORT', '5432')} "
            f"dbname={os.getenv('POSTGRES_DB', 'dpbps')} "
            f"user={os.getenv('POSTGRES_USER', 'dpbps_user')} "
            f"password={os.getenv('POSTGRES_PASSWORD', 'dpbps_pass')}"
        )
        pg8000.connect(conn_str).close()
        return True
    except Exception:
        return False

@pytest.fixture(scope="function")
def postgres_db(postgres_available):
    if not postgres_available:
        pytest.skip("PostgreSQL server not reachable")
    db = load_db_module("postgres")
    db.init_db()
    yield db
    # No explicit cleanup – test data uses unique IDs.

def test_postgres_initialisation(postgres_db):
    db = postgres_db
    with db.connection_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM product")
        count = cur.fetchone()[0]
        assert count > 0

def test_postgres_crud(postgres_db):
    db = postgres_db
    with db.connection_context() as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO product (id, name, description, price, inventory) VALUES ({db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER})",
            ("pg-prod-1", "PG Product", "PG Demo", 9.99, 10),
        )
        conn.commit()

        cur.execute(
            f"SELECT name, price FROM product WHERE id = {db.PLACEHOLDER}",
            ("pg-prod-1",),
        )
        row = cur.fetchone()
        assert row == ("PG Product", 9.99)

    # Transaction rollback test.
    with pytest.raises(RuntimeError):
        with db.connection_context() as conn:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO product (id, name, description, price, inventory) VALUES ({db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER})",
                ("pg-rollback", "Tmp", "Tmp", 1.0, 1),
            )
            raise RuntimeError("force rollback")
    with db.connection_context() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM product WHERE id = {db.PLACEHOLDER}", ("pg-rollback",))
        assert cur.fetchone() is None

# ---------------------------------------------------------------------------
# Cart service integration – uses the db abstraction directly.
# ---------------------------------------------------------------------------
def test_cart_service_sqlite(sqlite_db):
    db = sqlite_db
    user = "user-123"
    with db.connection_context() as conn:
        cur = conn.cursor()
        # Ensure cart exists.
        cur.execute(f"INSERT INTO cart (user_id) VALUES ({db.PLACEHOLDER})", (user,))
        cur.execute(
            f"INSERT INTO cart_item (cart_user_id, product_id, quantity) VALUES ({db.PLACEHOLDER}, {db.PLACEHOLDER}, {db.PLACEHOLDER})",
            (user, "prod-1", 2),
        )
        conn.commit()
        # Read back.
        cur.execute(
            f"SELECT product_id, quantity FROM cart_item WHERE cart_user_id = {db.PLACEHOLDER}",
            (user,),
        )
        rows = cur.fetchall()
        assert rows == [("prod-1", 2)]
