import os
import tempfile

os.environ["WORKBENCH_DATA"] = tempfile.mkdtemp(prefix="medical-ops-test-")

import pytest
from fastapi.testclient import TestClient
from backend.db import Base, Session, engine, initialize
from backend.main import app


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    initialize()
    yield


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value
