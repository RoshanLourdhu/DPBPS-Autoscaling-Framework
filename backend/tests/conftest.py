import os
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

@pytest.fixture(scope="session")
def client():
    # Ensure the simulation target points to the test client server
    os.environ["SIMULATION_TARGET_BASE_URL"] = "http://testserver"
    with TestClient(app) as c:
        yield c
