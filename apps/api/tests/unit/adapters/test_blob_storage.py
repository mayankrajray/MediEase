"""Blob storage adapters: write-once, atomic, contained (ADR-0012; M4-P4)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from mediease_api.adapters.storage.local import LocalBlobStorage
from mediease_api.adapters.storage.s3 import S3BlobStorage
from mediease_api.bootstrap import build_blob_storage
from mediease_api.config.settings import load_settings
from mediease_api.ports.storage import BlobStoragePort
from tests.conftest import SetEnv

KEY = "rx/0190a8e2-0000-7000-8000-000000000001/0190a8e2-0000-7000-8000-000000000002/v1.pdf"
BAD_KEYS = [
    "",
    "/etc/passwd",
    "../outside.pdf",
    "rx/../../outside.pdf",
    "rx/.hidden",
    "rx//v1.pdf",
    "rx\\v1.pdf",
    "rx/v1.pdf/",
]


@pytest.fixture
def local(tmp_path: Path) -> LocalBlobStorage:
    return LocalBlobStorage(tmp_path / "blobs")


@pytest.fixture
def s3() -> Iterator[S3BlobStorage]:
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket="mediease-test",
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        yield S3BlobStorage(client, "mediease-test")


@pytest.fixture(params=["local", "s3"])
def storage(request: pytest.FixtureRequest) -> BlobStoragePort:
    adapter: BlobStoragePort = request.getfixturevalue(request.param)
    return adapter


def test_put_get_exists(storage: BlobStoragePort) -> None:
    assert storage.get(KEY) is None
    assert not storage.exists(KEY)
    assert storage.put(KEY, b"%PDF-1", content_type="application/pdf") is True
    assert storage.exists(KEY)
    assert storage.get(KEY) == b"%PDF-1"


def test_r18_write_once_a_second_put_keeps_the_first_bytes(storage: BlobStoragePort) -> None:
    assert storage.put(KEY, b"first", content_type="application/pdf")
    assert storage.put(KEY, b"second", content_type="application/pdf") is False
    assert storage.get(KEY) == b"first"


def test_m6c_p1_delete_removes_an_object_and_a_repeat_is_harmless(
    storage: BlobStoragePort,
) -> None:
    """clinic-onboarding R13, R14: an application's certificates are deleted with it."""
    storage.put("applications/a1/doctor-1", b"%PDF-", content_type="application/pdf")
    storage.delete("applications/a1/doctor-1")
    assert not storage.exists("applications/a1/doctor-1")
    storage.delete("applications/a1/doctor-1")
    storage.delete("applications/never/doctor-9")


@pytest.mark.parametrize("key", BAD_KEYS)
def test_keys_cannot_escape_the_store(storage: BlobStoragePort, key: str) -> None:
    for call in (
        lambda: storage.put(key, b"x", content_type="application/pdf"),
        lambda: storage.get(key),
        lambda: storage.exists(key),
    ):
        with pytest.raises(ValueError, match="invalid blob key"):
            call()


def test_local_files_live_under_the_root(local: LocalBlobStorage, tmp_path: Path) -> None:
    local.put(KEY, b"x", content_type="application/pdf")
    assert (tmp_path / "blobs" / KEY).read_bytes() == b"x"


def test_local_put_is_atomic_and_leaves_no_temporary_file(
    local: LocalBlobStorage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_link(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "link", broken_link)
    with pytest.raises(OSError, match="disk full"):
        local.put(KEY, b"x", content_type="application/pdf")
    directory = (tmp_path / "blobs" / KEY).parent
    assert list(directory.iterdir()) == []
    assert not local.exists(KEY)


def test_local_put_loses_a_race_without_replacing_the_winner(
    local: LocalBlobStorage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another writer creates the file between the existence check and the link."""
    real_link = os.link

    def racing_link(src: str, dst: str) -> None:
        Path(dst).write_bytes(b"winner")
        real_link(src, dst)

    monkeypatch.setattr(os, "link", racing_link)
    assert local.put(KEY, b"loser", content_type="application/pdf") is False
    assert local.get(KEY) == b"winner"
    assert [p.name for p in (tmp_path / "blobs" / KEY).parent.iterdir()] == ["v1.pdf"]


def test_s3_objects_are_encrypted_and_typed(s3: S3BlobStorage) -> None:
    s3.put(KEY, b"%PDF-1", content_type="application/pdf")
    head = s3._client.head_object(Bucket="mediease-test", Key=KEY)
    assert head["ServerSideEncryption"] == "AES256"
    assert head["ContentType"] == "application/pdf"


def test_s3_other_errors_are_not_swallowed() -> None:
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        storage = S3BlobStorage(client, "no-such-bucket")
        from botocore.exceptions import ClientError

        for call in (
            lambda: storage.put(KEY, b"x", content_type="application/pdf"),
            lambda: storage.get(KEY),
        ):
            with pytest.raises(ClientError):
                call()


def test_s3_prefix_is_prepended() -> None:
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket="mediease-b", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        S3BlobStorage(client, "mediease-b", prefix="staging/").put(
            KEY, b"x", content_type="application/pdf"
        )
        assert client.get_object(Bucket="mediease-b", Key=f"staging/{KEY}")["Body"].read() == b"x"


def test_the_composition_root_picks_the_configured_store(
    set_env: SetEnv, valid_env: dict[str, str], tmp_path: Path
) -> None:
    set_env({**valid_env, "BLOB_LOCAL_DIR": str(tmp_path)})
    assert isinstance(build_blob_storage(load_settings()), LocalBlobStorage)
    set_env({**valid_env, "BLOB_STORAGE": "s3", "S3_BUCKET": "mediease-rx"})
    with mock_aws():
        assert isinstance(build_blob_storage(load_settings()), S3BlobStorage)
