# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Explicit hardware smoke check; run inside the extended image with GPU/NPU access."""

import json
import time

import numpy as np
import openvino as ov
from openvino import opset13 as ops


def main() -> None:
    core = ov.Core()
    print(
        json.dumps({"version": ov.get_version(), "available_devices": core.available_devices}),
        flush=True,
    )
    parameter = ops.parameter([1, 64], np.float32, name="input")
    weights = ops.constant(np.eye(64, dtype=np.float32))
    model = ov.Model([ops.relu(ops.matmul(parameter, weights, False, False))], [parameter])
    data = np.linspace(-1, 1, 64, dtype=np.float32).reshape(1, 64)
    failures = []
    for device in ("CPU", "GPU", "NPU"):
        if not any(
            item == device or item.startswith(device + ".") for item in core.available_devices
        ):
            failures.append(device)
            print(json.dumps({"device": device, "status": "UNAVAILABLE"}), flush=True)
            continue
        try:
            compiled = core.compile_model(model, device)
            execution = compiled.get_property("EXECUTION_DEVICES")
            actual = [execution] if isinstance(execution, str) else list(execution)
            if not actual or not all(
                item == device or item.startswith(device + ".") for item in actual
            ):
                raise RuntimeError(f"Unexpected execution device: {actual}")
            request = compiled.create_infer_request()
            deadline = time.monotonic() + 5
            count = 0
            while time.monotonic() < deadline:
                current = data if count % 2 == 0 else -data
                result = request.infer({0: current})[compiled.output(0)]
                np.testing.assert_allclose(result, np.maximum(current, 0), rtol=0.02, atol=0.002)
                count += 1
            print(
                json.dumps(
                    {"device": device, "status": "PASS", "executed_on": actual, "inferences": count}
                ),
                flush=True,
            )
        except (RuntimeError, AssertionError) as error:
            failures.append(device)
            print(json.dumps({"device": device, "status": "FAIL", "error": str(error)}), flush=True)
    if failures:
        raise SystemExit("Hardware inference not fully validated: " + ", ".join(failures))


if __name__ == "__main__":
    main()
