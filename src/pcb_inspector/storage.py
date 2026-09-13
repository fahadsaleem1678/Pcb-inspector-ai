import base64
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pcb_inspector.config import Settings
from uuid import uuid4


class ObjectStore(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Object key escapes the storage root")
        return path

    def put(self, key: str, content: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def make_store(settings: "Settings") -> ObjectStore:
    if settings.storage_backend == "local":
        return LocalObjectStore(settings.storage_path)
    from pcb_inspector.aws import aws_client

    return S3ObjectStore(aws_client("s3", settings), settings)


class S3ObjectStore:
    """Private, namespace-bound objects; all delivery stays behind API ownership checks."""

    def __init__(self, client: Any, settings: "Settings"):
        self.client = client
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix
        self.kms_key = settings.s3_kms_key_id
        # Decoded uploads can be larger than the compressed upload limit.
        self.max_bytes = settings.max_image_pixels * 4 + 1024 * 1024

    def key(self, key: str) -> str:
        if (
            not key
            or "\\" in key
            or any(p in ("", ".", "..") for p in key.split("/"))
            or any(ord(c) < 32 for c in key)
        ):
            raise ValueError("Invalid object key")
        result = f"{self.prefix}/{key}"
        if len(result.encode("utf-8")) > 1024:
            raise ValueError("Object key too long")
        return result

    def put(self, key: str, content: bytes) -> None:
        if len(content) > self.max_bytes:
            raise ValueError("Object exceeds storage size limit")
        digest = hashlib.sha256(content).digest()
        encryption = (
            {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key}
            if self.kms_key
            else {"ServerSideEncryption": "AES256"}
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=self.key(key),
            Body=content,
            ContentType="image/png" if key.endswith(".png") else "application/octet-stream",
            ChecksumSHA256=base64.b64encode(digest).decode("ascii"),
            Metadata={"sha256": digest.hex()},
            **encryption,
        )

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.key(key))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code == "NoSuchKey":
                raise FileNotFoundError(key) from exc
            raise
        body = response["Body"]
        try:
            if response["ContentLength"] > self.max_bytes:
                raise ValueError("Object exceeds storage size limit")
            content = body.read(self.max_bytes + 1)
            if len(content) > self.max_bytes or len(content) != response["ContentLength"]:
                raise ValueError("Object size mismatch")
            if hashlib.sha256(content).hexdigest() != response.get("Metadata", {}).get("sha256"):
                raise ValueError("Object checksum mismatch")
            return bytes(content)
        finally:
            body.close()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self.key(key))
