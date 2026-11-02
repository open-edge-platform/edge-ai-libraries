# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""RESTler value generators for task API stateful fuzzing."""

import json


def generate_task_registration_bodies(**kwargs):
    """Return a new valid full-mode task body for every prefix replay."""
    index = 0
    while True:
        index += 1
        yield json.dumps(
            {
                "task_name": f"restler_fuzz_task_{index}",
                "mode": "full",
                "content": {
                    "text": (
                        "GLOBAL_PROMPT='''Summarize the events. {question}'''\n\n"
                        "LOCAL_PROMPT='''Describe the clip from {st_tm} to {end_tm}.'''"
                    )
                },
            },
            separators=(",", ":"),
        )


value_generators = {
    "restler_custom_payload": {
        "/v1/tasks/post/__body__": generate_task_registration_bodies,
    },
}