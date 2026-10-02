"""Integration tests: /ready wired by the real composition root (NFR-12).

No fakes: create_app builds the engine and SqlAlchemyDatabaseCheck itself, so
this proves the production wiring against a real PostgreSQL.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
from flask.testing import FlaskClient
from sqlalchemy.engine import make_url

from mediease_api.bootstrap import create_app
from mediease_api.config.settings import load_settings
from tests.conftest import SetEnv


def _client_for(url: str, set_env: SetEnv, valid_env: dict[str, str]) -> FlaskClient:
    # APP_ENV=local: developer databases use the change-me password from .env.example.
    set_env({**valid_env, "APP_ENV": "local", "DATABASE_URL": url})
    return create_app(load_settings()).test_client()


@pytest.fixture(autouse=True)
def _password_never_logged(capsys: pytest.CaptureFixture[str], database_url: str) -> Iterator[None]:
    """Whatever these tests do, the database password never reaches the output."""
    yield
    password = make_url(database_url).password
    captured = capsys.readouterr()
    if password:
        assert password not in captured.out + captured.err


def test_nfr_12_ready_is_200_against_real_database(
    database_url: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    resp = _client_for(database_url, set_env, valid_env).get("/ready")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ready", "checks": {"database": "ok"}}


def test_nfr_12_ready_is_503_when_database_unreachable(
    database_url: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    url = make_url(database_url).set(host="127.0.0.1", port=closed_port)
    client = _client_for(url.render_as_string(hide_password=False), set_env, valid_env)

    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.get_json()["error"]["code"] == "READY_DB_UNAVAILABLE"
    assert client.get("/health").status_code == 200
