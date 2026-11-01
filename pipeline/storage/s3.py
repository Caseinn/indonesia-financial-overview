"""Shared S3-compatible client setup for the storage stages.

The storage stages talk to Cloudflare R2 through the S3 API, so the client
construction and the "object is absent" test live here once instead of being
repeated per stage.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from botocore.exceptions import ClientError

MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3Error(RuntimeError):
    """Raised when the object store cannot be configured from the environment."""


class ObjectStore(Protocol):
    """The slice of the S3 API the storage stages use, so tests can pass a stub."""

    def put_object(self, **kwargs: Any) -> Any: ...

    def get_object(self, **kwargs: Any) -> Any: ...

    def head_object(self, **kwargs: Any) -> Any: ...

    def list_objects_v2(self, **kwargs: Any) -> Any: ...


def is_missing(exc: ClientError) -> bool:
    """Report whether a ClientError means the object or bucket is absent."""
    return str(exc.response.get("Error", {}).get("Code", "")) in MISSING_CODES


def client_from_env() -> tuple[ObjectStore, str]:
    """Build an R2 S3 client and bucket name from the environment, or fail loudly."""
    env = {
        "R2_ENDPOINT": os.environ.get("R2_ENDPOINT"),
        "R2_ACCESS_KEY_ID": os.environ.get("R2_ACCESS_KEY_ID"),
        "R2_SECRET_ACCESS_KEY": os.environ.get("R2_SECRET_ACCESS_KEY"),
        "R2_BUCKET": os.environ.get("R2_BUCKET"),
    }
    missing = [name for name, value in env.items() if not value]
    if missing:
        raise S3Error(f"missing object-store environment: {', '.join(missing)}")

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=env["R2_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    return client, str(env["R2_BUCKET"])
