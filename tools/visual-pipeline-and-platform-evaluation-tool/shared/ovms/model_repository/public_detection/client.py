# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run the public OVMS object-detection MediaPipe graph once."""

import argparse
from pathlib import Path
import threading

import cv2
import numpy as np
import tritonclient.grpc as grpcclient


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--grpc-address", default="localhost:9000")
    parser.add_argument("--streaming", action="store_true")
    parser.add_argument("--frames", type=int, default=3)
    return parser.parse_args()


def create_input(image: np.ndarray) -> grpcclient.InferInput:
    infer_input = grpcclient.InferInput("input", image.shape, "UINT8")
    infer_input.set_data_from_numpy(np.ascontiguousarray(image))
    return infer_input


def run_stream(
    client: grpcclient.InferenceServerClient,
    image: np.ndarray,
    image_path: Path,
    frame_count: int,
) -> None:
    if frame_count < 1:
        raise ValueError("--frames must be at least 1")

    responses: dict[int, np.ndarray] = {}
    errors: list[BaseException] = []
    complete = threading.Event()
    lock = threading.Lock()

    def callback(
        result: grpcclient.InferResult | None, error: BaseException | None
    ) -> None:
        with lock:
            if error is not None:
                errors.append(error)
            elif result is not None:
                timestamp = (
                    result.get_response().parameters["OVMS_MP_TIMESTAMP"].int64_param
                )
                responses[timestamp] = result.as_numpy("annotated_image")
            if len(responses) + len(errors) == frame_count:
                complete.set()

    client.start_stream(callback=callback)
    try:
        for frame_id in range(frame_count):
            client.async_stream_infer(
                model_name="publicDetection",
                inputs=[create_input(image)],
                outputs=[grpcclient.InferRequestedOutput("annotated_image")],
                parameters={"OVMS_MP_TIMESTAMP": frame_id},
            )
        if not complete.wait(timeout=30):
            raise TimeoutError("Timed out waiting for streaming inference responses")
    finally:
        client.stop_stream()

    if errors:
        raise RuntimeError(f"Streaming inference failed: {errors[0]}")

    for frame_id, annotated_image in sorted(responses.items()):
        output_path = image_path.with_name(f"{image_path.stem}-stream-{frame_id}.jpg")
        cv2.imwrite(str(output_path), annotated_image)
        print(f"frame {frame_id}: {annotated_image.shape}; saved: {output_path}")


def main() -> None:
    arguments = parse_arguments()
    image = cv2.imread(str(arguments.image), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode image: {arguments.image}")

    client = grpcclient.InferenceServerClient(url=arguments.grpc_address)
    if arguments.streaming:
        run_stream(client, image, arguments.image, arguments.frames)
        return

    infer_input = create_input(image)
    outputs = [grpcclient.InferRequestedOutput("annotated_image")]
    response = client.infer(
        model_name="publicDetection",
        inputs=[infer_input],
        outputs=outputs,
    )

    annotated_image = response.as_numpy("annotated_image")
    output_path = arguments.image.with_name(f"{arguments.image.stem}-annotated.jpg")
    cv2.imwrite(str(output_path), annotated_image)
    print(f"annotated_image: {annotated_image.shape}; saved: {output_path}")


if __name__ == "__main__":
    main()
