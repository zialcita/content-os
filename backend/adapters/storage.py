from pathlib import Path

from adapters.base import AdapterResult, ProviderAdapter
from config import get_settings


class StorageAdapter(ProviderAdapter):
    name = "storage"

    def is_configured(self) -> bool:
        settings = get_settings()
        return settings.storage_backend == "r2" and bool(
            settings.s3_access_key_id and settings.s3_secret_access_key and settings.s3_bucket
        )

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> AdapterResult:
        if self.is_configured():
            return self._r2_stub(key)
        settings = get_settings()
        root = Path(settings.local_storage_dir)
        dest = root / key.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return AdapterResult(
            ok=True,
            provider="local",
            simulated=False,
            uri=f"file://{dest.resolve()}",
            payload={"content_type": content_type, "bytes": len(data)},
        )

    def _r2_stub(self, key: str) -> AdapterResult:
        # TODO: boto3 client(endpoint_url=S3_ENDPOINT_URL).put_object(...)
        settings = get_settings()
        return AdapterResult(
            ok=True,
            provider="r2",
            simulated=True,
            uri=f"s3://{settings.s3_bucket}/{key}",
            payload={"todo": True, "endpoint": settings.s3_endpoint_url},
        )


def get_storage() -> StorageAdapter:
    return StorageAdapter()
