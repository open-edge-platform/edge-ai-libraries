# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Frame Manager -- manages person frames in SeaweedFS (S3-compatible).

Bucket structure:
  loss-prevention-frames/
  +-- {object_id}/
  |   +-- {timestamp_1}.jpg    # Full camera frame
  |   +-- {timestamp_2}.jpg
  |   +-- ...                  # Rolling buffer of last 20 frames (~10s at 2fps)
  +-- alerts/
      +-- {alert_id}/
          +-- evidence/        # Frames sent to behavioral analysis, retained for audit

Only stores frames for individuals currently in HIGH_VALUE zones.
Storage rate: 2 fps per person in a high-value zone.
Rolling buffer: 20 frames per person.
"""

import base64
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog

from .config import ConfigService

logger = structlog.get_logger(__name__)

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    Minio = None
    S3Error = Exception
    logger.warning("minio package not installed — FrameManager will be no-op")


class FrameManager:
    """
    Manages person frames in SeaweedFS via S3-compatible API.

    Writes frames into the ``behavioral-frames`` bucket for the BA
    service to consume, and copies the suspect window into the
    ``alerts`` bucket when a suspicious BA result triggers an alert.
    """

    BA_BUCKET = "behavioral-frames"
    ALERTS_BUCKET = "alerts"

    def __init__(self, config: ConfigService) -> None:
        seaweed_cfg = config.get_seaweedfs_config()
        self.endpoint = seaweed_cfg.get("endpoint", "seaweedfs:8333")
        self.access_key = seaweed_cfg.get("access_key", "")
        self.secret_key = seaweed_cfg.get("secret_key", "")
        self.secure = seaweed_cfg.get("secure", False)
        self.retention_hours = seaweed_cfg.get("evidence_retention_hours", 24)
        self.exit_retention_seconds = seaweed_cfg.get("exit_retention_seconds", 60)

        # Per-person tracking of BA-bucket keys (used by cleanup helpers).
        self._person_ba_keys: Dict[str, List[str]] = {}
        # Per-visit tracking: last cutoff_ms copied to alerts bucket.
        # Key = src_prefix (visit path), value = last cutoff_ms copied.
        self._last_alert_cutoff: Dict[str, int] = {}

        self.client: Optional["Minio"] = None
        if Minio:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )

        logger.info(
            "FrameManager initialized",
            endpoint=self.endpoint,
            ba_bucket=self.BA_BUCKET,
            alerts_bucket=self.ALERTS_BUCKET,
        )

    async def ensure_bucket(self) -> None:
        """Create the frame buckets if they don't exist. Retries on connection failure."""
        if not self.client:
            return
        import asyncio
        for attempt in range(5):
            try:
                for bucket in (self.BA_BUCKET, self.ALERTS_BUCKET):
                    if not self.client.bucket_exists(bucket):
                        self.client.make_bucket(bucket)
                        logger.info("Created bucket", bucket=bucket)
                    else:
                        logger.info("Bucket exists", bucket=bucket)
                return
            except Exception:
                if attempt < 4:
                    wait = 2 * (attempt + 1)
                    logger.warning(
                        "SeaweedFS not ready, retrying",
                        attempt=attempt + 1,
                        wait=wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.exception("Bucket check/create failed after retries")

    # ---- Store person frame --------------------------------------------------
    def store_person_frame(
        self, object_id: str, image_bytes: bytes, ts: Optional[datetime] = None,
        region_id: Optional[str] = None,
        entry_timestamp: Optional[str] = None,
        scene_id: Optional[str] = None,
    ) -> str:
        """
        Store a full camera frame in the ``behavioral-frames`` bucket for the
        BA service to consume. Returns the SeaweedFS object key.
        """
        ts = ts or datetime.now(timezone.utc)
        prefix = f"{scene_id}/{object_id}" if scene_id else object_id

        # Behavioral-frames bucket layout:
        # {scene_id}/{person_id}/{region_id}/{entry_timestamp}/frames/{ts_ms}.jpg
        ts_ms = int(ts.timestamp() * 1000)
        entry_folder = ""
        if entry_timestamp:
            entry_folder = (
                entry_timestamp.replace(":", "").replace("-", "")
                .split("+")[0].split(".")[0]
            )
        if region_id and entry_folder:
            ba_key = f"{prefix}/{region_id}/{entry_folder}/frames/{ts_ms}.jpg"
        elif region_id:
            ba_key = f"{prefix}/{region_id}/frames/{ts_ms}.jpg"
        else:
            ba_key = f"{prefix}/frames/{ts_ms}.jpg"
        self._put(ba_key, image_bytes, bucket=self.BA_BUCKET)

        # Track BA keys for cleanup bookkeeping (no eviction — lifecycle is
        # owned by the visit-tracker driven cleanup paths).
        self._person_ba_keys.setdefault(object_id, []).append(ba_key)
        return ba_key

    # ---- Copy BA frames into alert bucket ------------------------------------
    def copy_frames_to_alert(
        self,
        scene_id: str,
        person_id: str,
        region_id: str,
        entry_timestamp: str,
        last_frame_ts: str,
        alert_id: str,
    ) -> int:
        """Copy this visit's behavioral-frames up to ``last_frame_ts`` into a
        per-alert prefix:

            ``{BA_BUCKET}/alerts/{person_id}/{alert_id}/frames/{ts_ms}.jpg``

        ``last_frame_ts`` is the SceneScape ISO string echoed in
        ``ba/results``; converted to epoch-ms it equals the filename used
        when the frame was first stored (see ``store_person_frame``). Any
        frames in the visit prefix whose filename ms <= cutoff_ms are
        copied.

        Returns the number of frames successfully copied. Originals are
        NOT deleted -- the visit cleanup path owns lifecycle.
        """
        if not (self.client and last_frame_ts and entry_timestamp):
            return 0

        cutoff_ms = self._iso_to_ms(last_frame_ts)
        if cutoff_ms is None:
            logger.warning(
                "copy_frames_to_alert: unparseable last_frame_ts",
                last_frame_ts=last_frame_ts,
                alert_id=alert_id,
            )
            return 0

        # Mirror the entry_folder transform used in store_person_frame.
        entry_folder = (
            entry_timestamp.replace(":", "").replace("-", "")
            .split("+")[0].split(".")[0]
        )
        person_prefix = f"{scene_id}/{person_id}" if scene_id else person_id
        src_prefix = f"{person_prefix}/{region_id}/{entry_folder}/frames/"
        dst_prefix = f"{person_id}/{alert_id}/frames/"

        copied = 0
        skipped = 0
        try:
            from minio.commonconfig import CopySource
        except ImportError:
            logger.exception("minio.commonconfig.CopySource unavailable")
            return 0

        try:
            objects = list(
                self.client.list_objects(
                    self.BA_BUCKET, prefix=src_prefix, recursive=True,
                )
            )
        except S3Error:
            logger.exception(
                "copy_frames_to_alert: list_objects failed",
                bucket=self.BA_BUCKET, prefix=src_prefix,
            )
            return 0

        # Only copy frames after the previous alert's cutoff for this visit.
        prev_cutoff = self._last_alert_cutoff.get(src_prefix, 0)

        for obj in objects:
            name = obj.object_name
            stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            try:
                ts_ms = int(stem)
            except ValueError:
                skipped += 1
                continue
            if ts_ms > cutoff_ms or ts_ms <= prev_cutoff:
                skipped += 1
                continue
            dst_key = f"{dst_prefix}{ts_ms}.jpg"
            try:
                self.client.copy_object(
                    self.ALERTS_BUCKET, dst_key,
                    CopySource(self.BA_BUCKET, name),
                )
                copied += 1
            except S3Error:
                logger.exception(
                    "copy_frames_to_alert: copy_object failed",
                    src=name, dst=dst_key,
                )

        # Update the cutoff so the next alert for this visit starts here.
        self._last_alert_cutoff[src_prefix] = cutoff_ms

        logger.info(
            "copy_frames_to_alert done",
            alert_id=alert_id,
            person_id=person_id,
            region_id=region_id,
            entry_timestamp=entry_timestamp,
            cutoff_ms=cutoff_ms,
            prev_cutoff=prev_cutoff,
            listed=len(objects),
            copied=copied,
            skipped=skipped,
            dst_bucket=self.ALERTS_BUCKET,
            dst_prefix=dst_prefix,
        )
        return copied

    @staticmethod
    def _iso_to_ms(iso_ts: str) -> Optional[int]:
        try:
            dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            return None

    # ---- Read frames ---------------------------------------------------------
    def get_frame(self, key: str) -> Optional[bytes]:
        """Read frame bytes by key."""
        return self._get(key)

    async def get_frames_base64(self, keys: List[str]) -> List[str]:
        """Fetch multiple frames and return as base64-encoded strings."""
        results = []
        for key in keys:
            raw = self._get(key)
            if raw:
                results.append(base64.b64encode(raw).decode("ascii"))
        return results

    def get_person_frame_keys(self, object_id: str) -> List[str]:
        """Return tracked behavioral-frames keys for a person."""
        return list(self._person_ba_keys.get(object_id, []))

    # ---- Cleanup -------------------------------------------------------------
    def cleanup_person(self, object_id: str, scene_id: Optional[str] = None) -> None:
        """
        Remove ALL frames for a person across every visit (called on session
        expiry / PERSON_LOST). Use ``cleanup_visit`` for per-visit cleanup
        on zone EXIT.
        """
        ba_keys = self._person_ba_keys.pop(object_id, [])
        prefix = f"{scene_id}/{object_id}/" if scene_id else f"{object_id}/"
        deleted = self._delete_prefix(prefix, bucket=self.BA_BUCKET)
        if ba_keys or deleted:
            logger.info(
                "Cleaned up person frames",
                object_id=object_id, tracked=len(ba_keys), deleted=deleted,
            )

    def cleanup_visit(
        self,
        object_id: str,
        region_id: str,
        entry_timestamp: str,
        scene_id: Optional[str] = None,
    ) -> None:
        """
        Remove ONLY this visit's behavioral-frames prefix:
            {scene_id}/{object_id}/{region_id}/{entry_folder}/

        Other visits (different entry_timestamp) for the same person and
        region remain intact, so the BA service can still process them.
        """
        if not entry_timestamp:
            logger.warning(
                "cleanup_visit called without entry_timestamp — skipping",
                object_id=object_id,
                region_id=region_id,
            )
            return
        # Mirror the entry_folder transform used by store_person_frame so
        # the prefix matches what was actually written.
        entry_folder = (
            entry_timestamp.replace(":", "").replace("-", "").split("+")[0].split(".")[0]
        )
        person_prefix = f"{scene_id}/{object_id}" if scene_id else object_id
        prefix = f"{person_prefix}/{region_id}/{entry_folder}/"
        logger.info(
            "cleanup_visit start",
            object_id=object_id,
            region_id=region_id,
            entry_timestamp=entry_timestamp,
            scene_id=scene_id,
            bucket=self.BA_BUCKET,
            prefix=prefix,
        )
        deleted = self._delete_prefix(prefix, bucket=self.BA_BUCKET)
        # Forget any tracked BA keys that fell under this prefix so the
        # in-memory list doesn't grow unbounded across visits.
        ba_keys = self._person_ba_keys.get(object_id, [])
        if ba_keys:
            kept = [k for k in ba_keys if not k.startswith(prefix)]
            self._person_ba_keys[object_id] = kept
            logger.info(
                "cleanup_visit pruned in-memory key list",
                object_id=object_id,
                before=len(ba_keys),
                after=len(kept),
            )
        logger.info(
            "cleanup_visit done",
            object_id=object_id,
            region_id=region_id,
            entry_timestamp=entry_timestamp,
            prefix=prefix,
            deleted=deleted,
        )

    def cleanup_person_frames_deferred(self, object_id: str) -> List[str]:
        """Return tracked BA-bucket keys for the person (caller schedules deletion)."""
        return list(self._person_ba_keys.get(object_id, []))

    # ---- Internal helpers ----------------------------------------------------
    def _put(self, key: str, data: bytes, bucket: Optional[str] = None) -> None:
        if not self.client:
            return
        bucket = bucket or self.BA_BUCKET
        try:
            self.client.put_object(
                bucket, key, io.BytesIO(data), length=len(data),
                content_type="image/jpeg",
            )
        except S3Error:
            logger.exception("SeaweedFS put failed", key=key, bucket=bucket)

    def _get(self, key: str, bucket: Optional[str] = None) -> Optional[bytes]:
        if not self.client:
            return None
        bucket = bucket or self.BA_BUCKET
        resp = None
        try:
            resp = self.client.get_object(bucket, key)
            return resp.read()
        except S3Error:
            logger.debug("SeaweedFS get miss", key=key, bucket=bucket)
            return None
        finally:
            if resp is not None:
                try:
                    resp.close()
                    resp.release_conn()
                except Exception:
                    pass

    def _delete(self, key: str, bucket: Optional[str] = None) -> None:
        if not self.client:
            return
        bucket = bucket or self.BA_BUCKET
        try:
            self.client.remove_object(bucket, key)
        except S3Error:
            logger.debug("SeaweedFS delete miss", key=key)

    def _delete_prefix(self, prefix: str, bucket: Optional[str] = None) -> int:
        """Delete all objects under a prefix in the given bucket.

        Returns the number of objects successfully removed.
        """
        if not self.client:
            return 0
        bucket = bucket or self.BA_BUCKET
        deleted = 0
        failed = 0
        try:
            objects = list(
                self.client.list_objects(bucket, prefix=prefix, recursive=True)
            )
            for obj in objects:
                try:
                    self.client.remove_object(bucket, obj.object_name)
                    deleted += 1
                except S3Error:
                    failed += 1
                    logger.warning(
                        "SeaweedFS object delete failed",
                        bucket=bucket,
                        key=obj.object_name,
                    )
            logger.info(
                "_delete_prefix complete",
                bucket=bucket,
                prefix=prefix,
                listed=len(objects),
                deleted=deleted,
                failed=failed,
            )
        except S3Error:
            logger.exception(
                "SeaweedFS list_objects failed during prefix delete",
                bucket=bucket,
                prefix=prefix,
            )
        return deleted
