import json
from minio import Minio

from src.utils.common import settings, logger

MINIO_URL = f"{settings.MINIO_HOST}:{settings.MINIO_API_PORT}"

client = Minio(
    MINIO_URL,
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=False,
)

logger.debug("initialized minio client")
