import io

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image

from pcb_inspector.api import create_app
from pcb_inspector.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("PCB_DATABASE_URL", url)
    monkeypatch.setenv("PCB_ENVIRONMENT", "test")
    command.upgrade(Config("alembic.ini"), "head")
    return Settings(
        _env_file=None,
        database_url=url,
        storage_path=tmp_path / "objects",
        environment="test",
        retry_delay_seconds=0,
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def png():
    output = io.BytesIO()
    Image.new("RGB", (128, 96), color=(24, 96, 64)).save(output, "PNG")
    return output.getvalue()
