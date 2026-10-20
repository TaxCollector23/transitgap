import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture(scope="session")
def client():
    # The MCP SDK session manager has one lifecycle per ASGI application.
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client
