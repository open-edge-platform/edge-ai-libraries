# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
SeaweedFS Client — reads and deletes behavioral-analysis frames.
"""

import logging
from typing import Optional
from datetime import datetime

import aioboto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SeaweedFSClient:
    """
    Async client for retrieving and deleting frames from SeaweedFS.

    Storage Structure:
        bucket: behavioral-frames
        └── {entity_id}/
            └── {region_id}/
                └── {entry_timestamp}/
                    └── frames/
                        ├── {timestamp_1}.jpg
                        ├── {timestamp_2}.jpg
                        └── ...

    Frames are stored with timestamp as filename for easy ordering.
    """

    def __init__(
        self,
        endpoint: str,
        bucket: str = "behavioral-frames",
        access_key: str = "",
        secret_key: str = "",
    ):
        self.endpoint = endpoint
        self.bucket = bucket
        self.access_key = access_key or None
        self.secret_key = secret_key or None
        self._anonymous = not self.access_key

        self.session = aioboto3.Session()

    def _get_client(self):
        """Get S3 client context manager."""
        kwargs = {
            "service_name": "s3",
            "endpoint_url": self.endpoint,
        }
        if self._anonymous:
            kwargs["config"] = BotoConfig(signature_version=UNSIGNED)
        else:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key
        return self.session.client(**kwargs)

    async def check_connection(self) -> bool:
        """Check if SeaweedFS is accessible."""
        try:
            async with self._get_client() as client:
                await client.head_bucket(Bucket=self.bucket)
                return True
        except Exception as e:
            logger.warning(f"SeaweedFS connection check failed: {e}")
            return False

    async def ensure_bucket(self):
        """Create bucket if it doesn't exist. Retries on connection failure."""
        import asyncio
        for attempt in range(5):
            try:
                async with self._get_client() as client:
                    try:
                        await client.head_bucket(Bucket=self.bucket)
                        logger.info(f"Bucket exists: {self.bucket}")
                    except client.exceptions.ClientError as e:
                        code = e.response.get("Error", {}).get("Code", "")
                        if code in ("404", "NoSuchBucket"):
                            await client.create_bucket(Bucket=self.bucket)
                            logger.info(f"Created bucket: {self.bucket}")
                        else:
                            raise
                return
            except Exception as e:
                err_name = type(e).__name__
                # BucketAlreadyExists means another service created it — that's fine
                if "BucketAlreadyExists" in str(e) or "BucketAlreadyExists" in err_name:
                    logger.info(f"Bucket already exists: {self.bucket}")
                    return
                if attempt < 4:
                    wait = 2 * (attempt + 1)
                    logger.warning(
                        f"SeaweedFS not ready, retrying in {wait}s (attempt {attempt + 1}): {e}"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Failed to ensure bucket after retries: {e}")
                    raise

    async def get_frames(
        self,
        entity_id: str,
        max_frames: int = 20,
        last_frame_ts: Optional[str] = None,
        region_id: Optional[str] = None,
        entry_timestamp: Optional[str] = None,
        scene_id: Optional[str] = None,
    ) -> list[tuple[np.ndarray, int]]:
        """
        Get frames for an entity, sorted by timestamp (oldest first).

        Args:
            entity_id: Entity identifier
            max_frames: Maximum number of frames to return
            last_frame_ts: Only return frames with timestamp <= this ISO
                           timestamp (e.g. "2026-04-30T06:53:16.387Z")
            region_id: Region/zone identifier
            entry_timestamp: Zone entry timestamp (compact ISO format)
            scene_id: Scene UUID prefix

        Returns:
            List of (frame_image, timestamp) tuples
        """
        # Parse last_frame_ts to epoch ms for comparison with frame filenames
        cutoff_ms: Optional[int] = None
        if last_frame_ts:
            try:
                dt = datetime.fromisoformat(last_frame_ts.replace("Z", "+00:00"))
                cutoff_ms = int(dt.timestamp() * 1000)
            except (ValueError, TypeError):
                logger.warning(f"Invalid last_frame_ts '{last_frame_ts}', ignoring")
                cutoff_ms = None

        # Build prefix: {scene_id}/{entity_id}/{region_id}/{entry_timestamp}/frames/
        base = f"{scene_id}/{entity_id}" if scene_id else entity_id
        if region_id and entry_timestamp:
            prefix = f"{base}/{region_id}/{entry_timestamp}/frames/"
        elif region_id:
            prefix = f"{base}/{region_id}/"
        else:
            prefix = f"{base}/"

        try:
            async with self._get_client() as client:
                # List all frames for this entity (recursively matches any entry_ts subfolder)
                response = await client.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=prefix,
                )

                if "Contents" not in response:
                    return []

                # Filter and sort by timestamp
                frame_keys = []
                for obj in response["Contents"]:
                    key = obj["Key"]
                    # Extract timestamp from filename
                    try:
                        filename = key.split("/")[-1]
                        timestamp = int(filename.replace(".jpg", ""))

                        if cutoff_ms is None or timestamp <= cutoff_ms:
                            frame_keys.append((key, timestamp))
                    except ValueError:
                        continue

                # Sort by timestamp (oldest first)
                frame_keys.sort(key=lambda x: x[1])

                # Limit to max_frames (take most recent)
                if len(frame_keys) > max_frames:
                    frame_keys = frame_keys[-max_frames:]

                # Fetch frames
                frames = []
                for key, timestamp in frame_keys:
                    try:
                        response = await client.get_object(
                            Bucket=self.bucket,
                            Key=key,
                        )
                        body = await response["Body"].read()

                        # Decode JPEG to numpy array
                        nparr = np.frombuffer(body, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                        if frame is not None:
                            frames.append((frame, timestamp))
                    except Exception as e:
                        logger.warning(f"Failed to fetch frame {key}: {e}")
                        continue

                logger.debug(f"Fetched {len(frames)} frames for entity {entity_id}")
                return frames

        except Exception as e:
            logger.error(f"Failed to get frames for {entity_id}: {e}")
            return []

    async def delete_frames(self, entity_id: str, region_id: Optional[str] = None,
                            scene_id: Optional[str] = None) -> int:
        """
        Delete all frames for an entity (optionally scoped to a region).

        Args:
            entity_id: Entity identifier
            region_id: Region/zone identifier (if None, deletes all frames for entity)
            scene_id: Scene UUID prefix

        Returns:
            Number of frames deleted
        """
        base = f"{scene_id}/{entity_id}" if scene_id else entity_id
        if region_id:
            prefix = f"{base}/{region_id}/frames/"
        else:
            prefix = f"{base}/"
        deleted_count = 0

        try:
            async with self._get_client() as client:
                # List all frames
                response = await client.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=prefix,
                )

                if "Contents" not in response:
                    return 0

                # Delete each frame
                for obj in response["Contents"]:
                    try:
                        await client.delete_object(
                            Bucket=self.bucket,
                            Key=obj["Key"],
                        )
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete {obj['Key']}: {e}")

            logger.info(f"Deleted {deleted_count} frames for entity {entity_id}")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete frames for {entity_id}: {e}")
            return deleted_count


