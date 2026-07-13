# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""SceneScape REST API client — fetches regions and authenticates via Token."""

from typing import Dict, List, Optional

import aiohttp
import structlog

from .config import ConfigService

logger = structlog.get_logger(__name__)


class SceneScapeClient:
    """
    Connects to the SceneScape REST API to fetch regions and map
    them to zone types using exact region names from zone_config.json.
    """

    def __init__(self, config: ConfigService) -> None:
        self.config = config
        api_cfg = config.get_scenescape_api_config()
        self.base_url = api_cfg.get("base_url", "https://web.scenescape.intel.com")
        self.auth_path = api_cfg.get("auth_path", "/api/v1/auth")
        self.scenes_path = api_cfg.get("scenes_path", "/api/v1/scenes")
        self.regions_path = api_cfg.get("regions_path", "/api/v1/regions")
        self.verify_ssl = api_cfg.get("verify_ssl", False)
        self._token: Optional[str] = None

    async def authenticate(self, username: str, password: str) -> bool:
        """Obtain an API token from SceneScape."""
        url = f"{self.base_url}{self.auth_path}"
        try:
            conn = aiohttp.TCPConnector(ssl=False) if not self.verify_ssl else None
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.post(
                    url,
                    json={"username": username, "password": password},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._token = data.get("token")
                        logger.info("SceneScape API authenticated")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(
                            "SceneScape auth failed",
                            status=resp.status,
                            body=body[:200],
                        )
                        return False
        except Exception as e:
            logger.error("SceneScape auth error", error=str(e))
            return False

    async def fetch_regions(self) -> List[dict]:
        """Fetch all regions from SceneScape REST API."""
        if not self._token:
            logger.warning("Not authenticated, cannot fetch regions")
            return []

        url = f"{self.base_url}{self.regions_path}"
        headers = {"Authorization": f"Token {self._token}"}
        try:
            conn = aiohttp.TCPConnector(ssl=False) if not self.verify_ssl else None
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # SceneScape API returns paginated: {count, results: [...]}
                        if isinstance(data, dict) and "results" in data:
                            regions = data["results"]
                        elif isinstance(data, list):
                            regions = data
                        else:
                            regions = []
                        logger.info("Fetched regions from SceneScape", count=len(regions))
                        return regions
                    else:
                        body = await resp.text()
                        logger.error(
                            "Failed to fetch regions",
                            status=resp.status,
                            body=body[:200],
                        )
                        return []
        except Exception as e:
            logger.error("SceneScape regions fetch error", error=str(e))
            return []

    async def fetch_scenes(self) -> List[dict]:
        """Fetch all scenes from SceneScape REST API."""
        if not self._token:
            logger.warning("Not authenticated, cannot fetch scenes")
            return []

        url = f"{self.base_url}{self.scenes_path}"
        headers = {"Authorization": f"Token {self._token}"}
        try:
            conn = aiohttp.TCPConnector(ssl=False) if not self.verify_ssl else None
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, dict) and "results" in data:
                            scenes = data["results"]
                        elif isinstance(data, list):
                            scenes = data
                        else:
                            scenes = []
                        logger.info("Fetched scenes from SceneScape", count=len(scenes))
                        return scenes
                    else:
                        body = await resp.text()
                        logger.error(
                            "Failed to fetch scenes",
                            status=resp.status,
                            body=body[:200],
                        )
                        return []
        except Exception as e:
            logger.error("SceneScape scenes fetch error", error=str(e))
            return []

    async def resolve_scene_id(self, scene_name: str) -> Optional[str]:
        """Look up a scene UUID by its human-readable name."""
        scenes = await self.fetch_scenes()
        for scene in scenes:
            if scene.get("name") == scene_name:
                uid = scene.get("uid", scene.get("uuid", ""))
                if uid:
                    logger.info("Scene resolved", scene_name=scene_name, scene_id=uid)
                    return uid
        logger.warning("Scene not found by name", scene_name=scene_name,
                       available=[s.get("name") for s in scenes])
        return None

    def map_zones(self, regions: List[dict]) -> Dict[str, dict]:
        """
        Match SceneScape regions to zone types using exact names from config.

        Returns {region_uuid: {"name": ..., "type": ..., "scene": ...}}
        """
        zone_name_map = self.config.get_zone_name_map()
        mapped: Dict[str, dict] = {}
        matched_names: set = set()

        for region in regions:
            uuid = region.get("uid", region.get("uuid", ""))
            name = region.get("name", "")
            scene = region.get("scene", "")

            if not uuid or not name:
                continue

            zone_type = zone_name_map.get(name)
            if zone_type:
                mapped[uuid] = {
                    "name": name,
                    "type": zone_type,
                    "scene": scene,
                }
                matched_names.add(name)
                logger.info(
                    "Zone mapped",
                    region_uuid=uuid,
                    region_name=name,
                    zone_type=zone_type,
                )

        # Warn about expected zones not found in SceneScape
        missing = set(zone_name_map.keys()) - matched_names
        for name in missing:
            logger.warning(
                "Expected zone not found in SceneScape — create a region with this name",
                zone_name=name,
                expected_type=zone_name_map[name],
            )

        return mapped

    async def discover_and_map(self, username: str, password: str) -> Dict[str, dict]:
        """Full flow: authenticate → fetch regions → map by name → return zones."""
        authenticated = await self.authenticate(username, password)
        if not authenticated:
            logger.warning("SceneScape auth failed, zone discovery skipped")
            return {}

        regions = await self.fetch_regions()
        if not regions:
            logger.warning("No regions found in SceneScape")
            return {}

        return self.map_zones(regions)
