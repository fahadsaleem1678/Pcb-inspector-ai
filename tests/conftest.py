import io
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from pcb_inspector.api import create_app
from pcb_inspector.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    database = os.environ.get("PCB_TEST_DATABASE_URL")
    admin = None
    schema = None
    url = f"sqlite:///{tmp_path / 'test.db'}"
    if database:
        parsed = make_url(database)
        if parsed.get_backend_name() != "postgresql":
            raise ValueError("PCB_TEST_DATABASE_URL must point to a disposable PostgreSQL database")
        schema = "pcb_test_" + uuid4().hex
        admin = create_engine(database)
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        url = parsed.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    monkeypatch.setenv("PCB_DATABASE_URL", url)
    monkeypatch.setenv("PCB_ENVIRONMENT", "test")
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield Settings(
            _env_file=None,
            database_url=url,
            storage_path=tmp_path / "objects",
            environment="test",
            auth_mode="local",
            retry_delay_seconds=0,
            storage_backend="local",
            queue_backend="database",
        )
    finally:
        if admin is not None and schema is not None:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            admin.dispose()


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
