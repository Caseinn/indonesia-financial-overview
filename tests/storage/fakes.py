"""In-memory S3 stub shared by the storage-stage tests."""

from __future__ import annotations

import io

from botocore.exceptions import ClientError


class FakeS3:
    """Minimal stand-in for the S3 calls the storage stages make."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.put_calls: list[str] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[Key] = (Body, ContentType)
        self.put_calls.append(Key)

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key][0])}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, Delimiter: str | None = None) -> dict:
        if Delimiter:
            children = {
                Prefix + key[len(Prefix) :].split("/", 1)[0] + "/"
                for key in self.objects
                if key.startswith(Prefix)
            }
            return {"CommonPrefixes": [{"Prefix": p} for p in sorted(children)]}
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        return {"Contents": [{"Key": key} for key in keys]}
