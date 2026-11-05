import asyncio
from io import BytesIO

from minio import Minio

from resume_ai.core.config import settings


class S3Storage:
    def __init__(self) -> None:
        self.client = Minio(
            endpoint=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=False,
        )
        self.bucket = settings.s3_bucket

    async def ensure_bucket(self) -> None:
        exists = await asyncio.to_thread(
            self.client.bucket_exists,
            self.bucket,
        )

        if not exists:
            await asyncio.to_thread(
                self.client.make_bucket,
                self.bucket,
            )

    async def upload(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            object_name,
            BytesIO(content),
            len(content),
            content_type=content_type,
        )

    async def download(self, object_name: str) -> bytes:
        def read_object() -> bytes:
            response = self.client.get_object(self.bucket, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(read_object)


storage = S3Storage()
