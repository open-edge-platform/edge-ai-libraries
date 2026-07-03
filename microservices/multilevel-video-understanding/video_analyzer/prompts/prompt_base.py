# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import string
from abc import ABC, abstractmethod

class BasePrompt(ABC):
	"""Abstract base for prompt builders."""
	task_name: str = ""
	# One-line human-readable description, surfaced by /v1/tasks so users can
	# tell what each registered task is for. Subclasses should override.
	DESCRIPTION: str = ""

	@staticmethod
	def _get_template_fields(template: str):
		fields = set()
		for literal, field_name, fmt_spec, conversion in string.Formatter().parse(template):
			if field_name:
				fields.add(field_name)
		return fields

	@abstractmethod
	def assign_global_prompt(self, **kwargs) -> str:
		pass

	@abstractmethod
	def assign_macro_prompt(self, **kwargs) -> str:
		pass

	@abstractmethod
	def assign_local_prompt(self, **kwargs) -> str:
		pass

	@abstractmethod
	def assign_t_minus_prompt(self, **kwargs) -> str:
		pass

	def _render_validated(
		self,
		template: str,
		kwargs: dict,
		optional_fields: set | None = None,
		auto_supplied_fields: set | None = None,
		extra_values: dict | None = None,
	) -> str:
		"""Render a template with strict field validation.

		- Validates that all required fields in `template` are present in `kwargs`.
		- Ignores any extra keys in `kwargs` that aren't used by the template.
		- Merges `extra_values` (e.g., internally supplied values) into formatting data.
		- `optional_fields` are allowed to be missing; they default to empty strings.
		- `auto_supplied_fields` are excluded from required checks (provided via `extra_values`).

		Returns the rendered string. Raises `ValueError` if required fields are missing.
		"""
		optional_fields = optional_fields or set()
		auto_supplied_fields = auto_supplied_fields or set()
		extra_values = extra_values or {}

		fields = self._get_template_fields(template)
		required_fields = fields - optional_fields - auto_supplied_fields

		provided_keys = set(kwargs.keys())
		missing = required_fields - provided_keys
		if missing:
			raise ValueError(f"Missing required fields: {sorted(missing)}")

		format_values = {}
		# Required fields come from kwargs
		for k in required_fields:
			format_values[k] = str(kwargs[k])
		# Optional fields default to empty string when not provided
		for k in (fields & optional_fields):
			val = kwargs.get(k, '')
			format_values[k] = '' if val is None else str(val)
		# Auto-supplied and other explicit values
		for k, v in extra_values.items():
			format_values[k] = '' if v is None else str(v)

		return template.format(**format_values)