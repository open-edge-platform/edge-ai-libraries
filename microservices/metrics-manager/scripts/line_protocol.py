# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helpers shared by the execd readers that print InfluxDB line protocol."""


def escape_tag_value(value: str) -> str:
    """Escape a tag value for InfluxDB line protocol.

    Commas, equals signs and spaces are the separators of the tag set, so a
    value containing any of them (e.g. a METRICS_MANAGER_HOSTNAME of
    "rack 1,node=a") would otherwise split into extra tags and produce a line
    Telegraf rejects.
    """
    return value.replace(",", r"\,").replace("=", r"\=").replace(" ", r"\ ")
