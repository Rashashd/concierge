"""MinIO / S3 object storage adapter.

All objects for a tenant live under tenants/{tenant_id}/.
Erasure deletes the entire prefix.
"""

import asyncio
import json
from typing import Any
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

    def _content_key(self, tenant_id: UUID, content_id: UUID) -> str:
        return f"tenants/{tenant_id}/content/{content_id}.json"

    async def put_content(
        self,
        tenant_id: UUID,
        content_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        """Write a content item blob under tenants/{tenant_id}/content/{id}.json."""
        key = self._content_key(tenant_id, content_id)
        body = json.dumps(payload, default=str).encode()
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        logger.info("minio.content_put", key=key)

    async def delete_content(self, tenant_id: UUID, content_id: UUID) -> None:
        """Delete a single content item blob."""
        key = self._content_key(tenant_id, content_id)
        await asyncio.to_thread(
            self._s3.delete_object,
            Bucket=self._bucket,
            Key=key,
        )
        logger.info("minio.content_deleted", key=key)

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
