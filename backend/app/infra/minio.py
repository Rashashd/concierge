"""MinIO / S3 object storage adapter.

All objects for a tenant live under tenants/{tenant_id}/.
Erasure deletes the entire prefix.
"""

import asyncio
from uuid import UUID

import boto3
import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


class MinioClient:
    def __init__(self, settings: Settings) -> None:
        endpoint = settings.minio_endpoint
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"
        self._bucket = settings.minio_bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
        )

    def tenant_prefix(self, tenant_id: UUID) -> str:
        return f"tenants/{tenant_id}/"

    async def delete_tenant_prefix(self, tenant_id: UUID) -> int:
        """Delete all objects under tenants/{tenant_id}/. Returns count deleted."""
        return await asyncio.to_thread(self._delete_prefix_sync, tenant_id)

    def _delete_prefix_sync(self, tenant_id: UUID) -> int:
        prefix = self.tenant_prefix(tenant_id)
        paginator = self._s3.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if not objects:
                continue
            self._s3.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            deleted += len(objects)
        logger.info("minio.prefix_deleted", prefix=prefix, count=deleted)
        return deleted
