"""Strong ETags and If-None-Match (M3-P4; spec R12, D23; RFC 9110 §13.1.2)."""

from __future__ import annotations

import pytest
from flask import Flask

from mediease_api.delivery.http.etag import TAG_LENGTH, conditional_json, strong_tag


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)

    @app.get("/thing")
    def thing():  # type: ignore[no-untyped-def]
        return conditional_json({"b": 2, "a": [1, "x"]})

    return app


def test_the_same_body_gives_the_same_tag_and_any_change_another() -> None:
    assert strong_tag(b'{"a":1}') == strong_tag(b'{"a":1}')
    assert strong_tag(b'{"a":1}') != strong_tag(b'{"a":2}')
    assert len(strong_tag(b"")) == TAG_LENGTH


def test_r12_a_200_carries_a_strong_tag_and_a_match_is_a_bodiless_304(app: Flask) -> None:
    client = app.test_client()
    first = client.get("/thing")
    assert first.status_code == 200
    tag, weak = first.get_etag()
    assert tag == strong_tag(first.get_data()) and weak is False
    assert first.headers["ETag"] == f'"{tag}"'

    again = client.get("/thing", headers={"If-None-Match": f'"{tag}"'})
    assert again.status_code == 304
    assert again.get_data() == b""
    assert again.headers["ETag"] == f'"{tag}"'


@pytest.mark.parametrize(
    "header",
    ['"other", "{tag}"', "*", 'W/"{tag}"'],
    ids=["in-a-list", "star", "weak-form-compares-weakly"],
)
def test_if_none_match_is_compared_as_rfc_9110_says(app: Flask, header: str) -> None:
    client = app.test_client()
    tag = client.get("/thing").get_etag()[0]
    resp = client.get("/thing", headers={"If-None-Match": header.format(tag=tag)})
    assert resp.status_code == 304


@pytest.mark.parametrize("header", ['"stale"', "", "not-a-tag"])
def test_anything_else_gets_the_body(app: Flask, header: str) -> None:
    resp = app.test_client().get("/thing", headers={"If-None-Match": header})
    assert resp.status_code == 200
    assert resp.get_json() == {"a": [1, "x"], "b": 2}
