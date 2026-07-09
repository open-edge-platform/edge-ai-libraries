# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Alert Service Client — calls the external AlertService via HTTP.

The AlertService (separate container) handles:
  - Alert publication to configured destinations (MQTT, webhook, logging)
  - Alert type registration and schema validation
  - Deduplication to prevent alert flooding
  - Severity levels and escalation rules
  - Alert history for audit

This client sends Alert objects from the LP service to the AlertService.
When the AlertService is unavailable, alerts fall back to local publishing.
"""

from typing import Any, Dict, List, Optional
import os

import aiohttp
import structlog

from models.alerts import Alert
from .config import ConfigService

logger = structlog.get_logger(__name__)


class AlertServiceClient:
    """
    HTTP client for the external AlertService.

    Sends alerts for publication, deduplication, and routing.
    Falls back gracefully when the service is unavailable.
    """

    def __init__(self, config: ConfigService) -> None:
        alert_cfg = config.get_alert_service_config()
        self.base_url = os.environ.get(
            "ALERT_SERVICE_URL",
            alert_cfg.get("base_url", "http://alert-service:8000"),
        )
        self.timeout = alert_cfg.get("timeout_seconds", 10)
        self.enabled = alert_cfg.get("enabled", True)

        logger.info(
            "AlertServiceClient initialized",
            base_url=self.base_url,
            enabled=self.enabled,
        )

    async def publish_alert(self, alert: Alert) -> Optional[Dict[str, Any]]:
        """
        Send an alert to the external AlertService.

        Payload matches the AlertService contract:
            {
                "alert_type": "CONCEALMENT" | ...,
                "metadata": {
                    "alert_id": UUID,
                    "poi_id": str,
                    "camera_id": str,
                    "zone_id": str,
                    "zone_name": str,
                    ...
                },
                "payload": {
                    "severity": "WARNING" | "CRITICAL",
                    "evidence": [str],
                    ...details
                },
                "timestamp": ISO datetime
            }

        Returns the AlertService response dict, or None on failure.
        """
        if not self.enabled:
            return None

        payload = {
            "alert_type": getattr(alert.alert_type, "value", alert.alert_type),
            "timestamp": alert.timestamp.isoformat(),
            "metadata": {
                "alert_id": alert.alert_id,
                "person_id": alert.object_id,
                "zone_id": alert.region_id or "",
                "zone_name": alert.region_name or "",
                "severity": getattr(alert.alert_level, "value", alert.alert_level),
                **alert.details,
            },
            "payload": {
                "severity": getattr(alert.alert_level, "value", alert.alert_level),
                "evidence": alert.evidence_keys,
                **alert.details,
            },
        }

        return await self._post("/api/v1/alerts", payload)

    async def get_alerts(
        self,
        alert_type: Optional[str] = None,
        object_id: Optional[str] = None,
        limit: int = 50,
    ) -> Optional[List[Dict[str, Any]]]:
        """Retrieve alerts from the AlertService (for audit/history)."""
        if not self.enabled:
            return None

        params = {"limit": limit}
        if alert_type:
            params["alert_type"] = alert_type
        if object_id:
            params["object_id"] = object_id

        return await self._get("/api/v1/alerts", params)

    async def health_check(self) -> bool:
        """Check if the AlertService is available."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    # ---- internal ------------------------------------------------------------
    async def _post(
        self, path: str, payload: dict
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    body = await resp.text()
                    logger.error(
                        "AlertService publish failed",
                        path=path,
                        status=resp.status,
                        body=body[:200],
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.error("AlertService connection error", path=path, error=str(e))
            return None
        except Exception:
            logger.exception("AlertService call error", path=path)
            return None

    async def _get(
        self, path: str, params: Optional[dict] = None
    ) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 405:
                        # Alert service does not support GET queries
                        logger.debug("AlertService does not support GET %s", path)
                        return None
                    body = await resp.text()
                    logger.error(
                        "AlertService query failed",
                        path=path,
                        status=resp.status,
                        body=body[:200],
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.error("AlertService connection error", path=path, error=str(e))
            return None
        except Exception:
            logger.exception("AlertService call error", path=path)
            return None
