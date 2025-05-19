import time
from typing import List, Dict, Tuple
import logging
from utils import run_pipeline_and_extract_metrics
import math

logging.basicConfig(level=logging.INFO)


class Benchmark:
    def __init__(
        self,
        video_path: str,
        pipeline_cls,
        fps_floor: float,
        rate: int,
        parameters: Dict[str, str],
        constants: Dict[str, str],
        elements: List[tuple[str, str, str]] = [],
    ):
        self.video_path = video_path
        self.pipeline_cls = pipeline_cls
        self.fps_floor = fps_floor
        self.rate = rate
        self.parameters = parameters
        self.constants = constants
        self.elements = elements
        self.best_result = None
        self.results = []

        self.logger = logging.getLogger("Benchmark")



    def run(self) ->Tuple[int, int, int, float]:
        start_time = time.time()
        streams = 1
        last_estimate = -1
        max_duration = 300  # 5 minutes
        last_good_config = []

        while True:
            if time.time() - start_time > max_duration:
                self.logger.info("Stopping: Max time reached.")
                break
            ai_streams = math.ceil(streams * (self.rate / 100))
            non_ai_streams = streams - ai_streams
            results = run_pipeline_and_extract_metrics(
                pipeline_cmd=self.pipeline_cls,
                constants=self.constants,
                parameters=self.parameters,
                channels=(non_ai_streams, ai_streams),
                elements=self.elements
            )
            if not results:
                self.logger.warning("No results returned, exiting.")
                break

            result = results[0]
            try:
                total_fps = float(result["total_fps"])
                per_stream_fps = float(result["per_stream_fps"])
                if per_stream_fps >= self.fps_floor:
                    self.logger.info("Per stream FPS above floor")
                    new_estimate = math.floor(total_fps / self.fps_floor)
                    last_good_config.append((
                        result["num_streams"],
                        ai_streams,
                        non_ai_streams,
                        per_stream_fps,
                    ))
                    if new_estimate == last_estimate or \
                        (len(last_good_config) >= 2 and new_estimate == last_good_config[-2][0]):
                            self.logger.info(f"Estimate converged at {new_estimate}.")
                            break
                    last_estimate = new_estimate
                    streams = new_estimate
                else:
                    self.logger.info("Per stream FPS below floor, decreasing stream count.")
                    new_estimate = max(1, streams - 1)
                    last_good_config.append((
                        result["num_streams"],
                        ai_streams,
                        non_ai_streams,
                        per_stream_fps,
                    ))
                    if new_estimate == last_estimate or \
                        (len(last_good_config) >= 2 and new_estimate == last_good_config[-2][0]):
                            self.logger.info(f"Estimate converged at lower {new_estimate}.")
                            break
                    last_estimate = new_estimate
                    streams = new_estimate
            except (KeyError, ValueError) as e:
                self.logger.error(f"Invalid result encountered: {e}")
                break

        return last_good_config[-1] if last_good_config else (0, 0, 0, 0.0)
