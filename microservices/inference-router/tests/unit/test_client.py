# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from typing import Any

import requests


class GatewayTestClient:
	def __init__(self, base_url: str | None = None, timeout: float = 120.0) -> None:
		self.base_url = (base_url or os.getenv("GATEWAY_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
		self.timeout = timeout
		self.session = requests.Session()

	def health(self) -> dict[str, Any]:
		return self._request("GET", "/health")

	def list_models(self) -> dict[str, Any]:
		return self._request("GET", "/v1/models")

	def chat_completion(
		self,
		*,
		model: str,
		messages: list[dict[str, Any]],
		**extra_payload: Any,
	) -> dict[str, Any]:
		payload = {
			"model": model,
			"messages": messages,
			"chat_template_kwargs": {
				"enable_thinking": False
			},
			**extra_payload,
		}
		return self._request("POST", "/v1/chat/completions", json=payload)

	def get_stats(self) -> dict[str, Any]:
		return self._request("GET", "/v1/metrics")

	def reset_stats(self) -> dict[str, Any]:
		return self._request("POST", "/v1/metrics/reset")

	def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
		response = self.session.request(
			method=method,
			url=f"{self.base_url}{path}",
			timeout=kwargs.pop("timeout", self.timeout),
			**kwargs,
		)
		try:
			response.raise_for_status()
		except requests.HTTPError as exc:
			body = response.text.strip()
			detail = f"{exc}. Response body: {body}" if body else str(exc)
			raise AssertionError(detail) from exc
		return response.json()
