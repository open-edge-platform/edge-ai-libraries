import time
from typing import List, Dict, Tuple
import logging
from utils import run_pipeline_and_extract_metrics

logging.basicConfig(level=logging.INFO)


class Benchmark:
    def __init__(
        self,
        video_path: str,
        pipeline_cls,
        fps_floor: float,
        parameters: Dict[str, str],
        constants: Dict[str, str],
        elements: List[tuple[str, str, str]] = [],
    ):
        self.video_path = video_path
        self.pipeline_cls = pipeline_cls
        self.fps_floor = fps_floor
        self.parameters = parameters
        self.constants = constants
        self.elements = elements
        self.best_result = None
        self.results = []

        self.logger = logging.getLogger("Benchmark")

    def run(self) -> Tuple[int, int, int, float]:
        start_time = time.time()
        streams = 1
        last_good_config = (0, 0, 0, 0.0)

        # Phase 1: Exponential Expansion
        while True:
            if time.time() - start_time > 300:
                self.logger.info("Time limit reached during exponential phase")
                break

            ai_streams = max(1, int(streams * 0.2))
            non_ai_streams = streams - ai_streams
            results = run_pipeline_and_extract_metrics(
                self.pipeline_cls,
                constants=self.constants,
                parameters=self.parameters,
                channels=(non_ai_streams, ai_streams),
                elements=self.elements,
            )
            result = results[0]

            try:
                raw_fps_value = result["per_stream_fps"]
                per_stream_fps = float(raw_fps_value)
                if per_stream_fps >= self.fps_floor:
                    last_good_config = (
                        result["num_streams"],
                        ai_streams,
                        non_ai_streams,
                        per_stream_fps,
                    )
                    streams *= 2
                else:
                    failed_streams = streams
                    break
            except (ValueError, TypeError):
                self.logger.info(
                    "Invalid FPS value, skipping this result:", per_stream_fps
                )
                failed_streams = streams
                break

        # Phase 2: Binary Search
        low = last_good_config[0] + 1
        high = failed_streams - 1
        best_config = last_good_config

        while low <= high:
            if time.time() - start_time > 300:
                self.logger.info("Time limit reached during Binary phase.")
                break
            mid = (low + high) // 2
            ai_streams = max(1, int(mid * 0.2))
            non_ai_streams = mid - ai_streams

            results = run_pipeline_and_extract_metrics(
                self.pipeline_cls,
                constants=self.constants,
                parameters=self.parameters,
                channels=(non_ai_streams, ai_streams),
                elements=self.elements,
            )

            if not results:
                self.logger.info(
                    "No results returned from run_pipeline_and_extract_metrics"
                )
                break

            result = results[0]

            per_stream_fps = float(result["per_stream_fps"])
            if (
                isinstance(per_stream_fps, (int, float))
                and per_stream_fps >= self.fps_floor
            ):
                if result["num_streams"] > best_config[0]:
                    best_config = (mid, ai_streams, non_ai_streams, per_stream_fps)
                low = mid + 1
            else:
                high = mid - 1

        return best_config
