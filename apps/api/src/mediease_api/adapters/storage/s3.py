"""Blob storage on an S3-compatible object store (production from M6; ADR-0012).

Write-once through a conditional ``PutObject`` (``If-None-Match: *``): the store refuses to
replace an existing key, so two writers cannot overwrite each other. Objects are encrypted at
rest (``ServerSideEncryption=AES256``) and private: the bucket must block public access, and we
never hand out pre-signed URLs; the API streams objects to authorised staff.

The client is built in the composition root from settings, with credentials from the standard
AWS chain (environment or instance role), never from code. Tests use ``moto`` in-process, so
nothing leaves the machine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from mediease_api.adapters.storage import check_key

if TYPE_CHECKING:
    from types_boto3_s3.client import S3Client

_EXISTS = {"PreconditionFailed", "ConditionalRequestConflict", "412"}
_MISSING = {"NoSuchKey", "404", "NotFound"}


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class S3BlobStorage:
    def __init__(self, client: S3Client, bucket: str, *, prefix: str = "") -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return self._prefix + check_key(key)

    def put(self, key: str, data: bytes, *, content_type: str) -> bool:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._key(key),
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if _code(exc) in _EXISTS:
                return False
            raise
        return True

    def get(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
        except ClientError as exc:
            if _code(exc) in _MISSING:
                return None
            raise
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(key))
        except ClientError as exc:
            if _code(exc) in _MISSING:
                return False
            raise
        return True
