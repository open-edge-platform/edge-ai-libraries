# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import FederationConfig
from .health import HealthMonitor
from .scheduler import FederationScheduler, NoCapacityError

logger = logging.getLogger(__name__)


def create_app(config: FederationConfig) -> FastAPI:
    client = httpx.AsyncClient(timeout=config.request_timeout)
    scheduler = FederationScheduler(config.nodes, client)
    health_monitor = HealthMonitor(
        config.nodes, interval=config.health_check_interval
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        health_monitor.start()
        yield
        await health_monitor.stop()
        await client.aclose()

    app = FastAPI(
        title="DLS-PS Federation Proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _resolve_instance(composite_id: str):
        try:
            node_id, instance_id = scheduler.resolve_composite_id(composite_id)
        except ValueError:
            raise HTTPException(400, f"Invalid instance ID format: {composite_id}")
        node = scheduler.nodes.get(node_id)
        if not node:
            raise HTTPException(404, f"Unknown node: {node_id}")
        return node, instance_id

    # --- Pipeline template listing ---

    @app.get("/pipelines")
    async def list_pipelines():
        """Fan-out to all nodes, return deduplicated pipeline templates."""
        tasks = [
            client.get(f"{node.url}/pipelines")
            for node in scheduler.nodes.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen: set[tuple[str, str]] = set()
        merged = []
        for resp in results:
            if isinstance(resp, Exception) or resp.status_code != 200:
                continue
            for pipeline in resp.json():
                key = (pipeline.get("name", ""), pipeline.get("version", ""))
                if key not in seen:
                    seen.add(key)
                    merged.append(pipeline)
        return merged

    # --- Aggregated status (defined before /{instance_id} to avoid conflict) ---

    @app.get("/pipelines/status")
    async def get_all_status():
        """Fan-out to all nodes, merge pipeline instance statuses."""
        tasks = [
            client.get(f"{node.url}/pipelines/status")
            for node in scheduler.nodes.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged = []
        for node, resp in zip(scheduler.nodes.values(), results):
            if isinstance(resp, Exception) or resp.status_code != 200:
                continue
            for status in resp.json():
                status["id"] = scheduler.make_composite_id(
                    node.id, str(status["id"])
                )
                status["node"] = node.id
                merged.append(status)
        return merged

    # --- Pipeline start (capacity-scheduled) ---

    @app.post("/pipelines/{name}/{version}")
    async def start_pipeline(name: str, version: str, request: Request):
        """Schedule a new pipeline to the least-loaded healthy node."""
        body = await request.body()
        try:
            node = await scheduler.select_node()
        except NoCapacityError:
            raise HTTPException(503, "No healthy nodes with available capacity")

        resp = await client.post(
            f"{node.url}/pipelines/{name}/{version}",
            content=body,
            headers={"content-type": "application/json"},
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(resp.status_code, resp.text)

        instance_id = resp.json()
        composite_id = scheduler.make_composite_id(node.id, str(instance_id))
        scheduler.register_instance(composite_id, node.id)
        logger.info(
            "Started pipeline %s/%s on %s as %s",
            name, version, node.id, composite_id,
        )
        return composite_id

    # --- Instance-routed endpoints ---

    @app.get("/pipelines/{instance_id}/status")
    async def get_instance_status(instance_id: str):
        """Route status request to the owning node."""
        node, real_id = _resolve_instance(instance_id)
        resp = await client.get(f"{node.url}/pipelines/{real_id}/status")
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        data = resp.json()
        data["id"] = instance_id
        data["node"] = node.id
        return data

    @app.get("/pipelines/{instance_id}")
    async def get_instance(instance_id: str):
        """Route instance summary request to the owning node."""
        node, real_id = _resolve_instance(instance_id)
        resp = await client.get(f"{node.url}/pipelines/{real_id}")
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        data = resp.json()
        data["id"] = instance_id
        data["node"] = node.id
        return data

    @app.delete("/pipelines/{instance_id}")
    async def delete_instance(instance_id: str):
        """Stop pipeline on the owning node."""
        node, real_id = _resolve_instance(instance_id)
        resp = await client.delete(f"{node.url}/pipelines/{real_id}")
        scheduler.unregister_instance(instance_id)
        if resp.status_code not in (200, 204):
            raise HTTPException(resp.status_code, resp.text)
        if resp.status_code == 204:
            return Response(status_code=204)
        return resp.json()

    # --- Forward request to existing instance ---

    @app.post("/pipelines/{name}/{version}/{instance_id}")
    async def post_to_instance(
        name: str, version: str, instance_id: str, request: Request
    ):
        """Forward a request to an existing pipeline instance."""
        node, real_id = _resolve_instance(instance_id)
        body = await request.body()
        resp = await client.post(
            f"{node.url}/pipelines/{name}/{version}/{real_id}",
            content=body,
            headers={"content-type": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

    # --- Model download forwarding ---

    @app.post("/pipelines/{name}/{version}/{instance_id}/models")
    async def post_instance_models(
        name: str, version: str, instance_id: str, request: Request
    ):
        """Forward model download request to the owning node."""
        node, real_id = _resolve_instance(instance_id)
        body = await request.body()
        resp = await client.post(
            f"{node.url}/pipelines/{name}/{version}/{real_id}/models",
            content=body,
            headers={"content-type": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

    # --- Federation-specific endpoint ---

    @app.get("/nodes")
    async def list_nodes():
        """List registered nodes with current health status."""
        return [
            {
                "id": node.id,
                "url": node.url,
                "max_pipelines": node.max_pipelines,
                "healthy": health_monitor.node_healthy.get(node.id, False),
            }
            for node in scheduler.nodes.values()
        ]

    return app
