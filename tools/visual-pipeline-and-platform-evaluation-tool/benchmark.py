import subprocess
import time
from typing import List, Dict, Tuple
import re
import tempfile
from pipeline import SmartNVRPipeline, Transportation2Pipeline
from utils import run_pipeline_and_extract_metrics

class benchmark:
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

   def run(self) -> Tuple[int, int, int, float]:
       start_time = time.time()
       streams = 1
       last_good_config = (0, 0, 0, 0.0)
      
       # Phase 1: Exponential Expansion
       while True:
           if time.time() - start_time > 300:
               print("Time limit reached during exponential phase")
               continue
           #ai_streams = max(1, int(streams * 0.2)) if self.model_type == "smartnvr" else streams
           #non_ai_streams = streams - ai_streams if self.model_type == "smartnvr" else 0
           ai_streams = max(1, int(streams * 0.2))
           non_ai_streams = streams - ai_streams
        #    if isinstance(self.parameters["object_detection_device"], list):
        #        self.parameters["object_detection_device"] = self.parameters["object_detection_device"][0]
           results = run_pipeline_and_extract_metrics(self.pipeline_cls, constants=self.constants, parameters=self.parameters, channels=(non_ai_streams, ai_streams), elements=self.elements)
           result = results[0]
           
           try:
                if result["per_stream_fps"] >= self.fps_floor:
                        last_good_config = (result["num_streams"], ai_streams, non_ai_streams, result["per_stream_fps"])
                        streams *= 2  # Exponential doubling
                else:
                        failed_streams = streams
                        break
           except (ValueError, TypeError):
                print("Invalid FPS value, skipping this result:", result["per_stream_fps"])
                failed_streams = streams
                break
           
       # Phase 2: Binary Search 
       low = last_good_config[0] + 1
       high = failed_streams
       best_config = last_good_config
    
       print("Next Binary Search")
       while low <= high:
            if time.time() - start_time > 300:
                print("Time limit reached during linear phase.")
                continue
            mid = (low + high)//2
            #ai_streams = max(1, int(mid * 0.2)) if self.model_type == "smartnvr" else mid
            #non_ai_streams = mid - ai_streams if self.model_type == "smartnvr" else 0
            ai_streams = max(1, int(streams * 0.2))
            non_ai_streams = mid - ai_streams

            #pipeline = self.pipeline_cls()
            results = run_pipeline_and_extract_metrics(self.pipeline_cls, constants=self.constants, parameters=self.parameters, channels=(non_ai_streams, ai_streams), elements=self.elements)
            
            if not results:
                print("No results returned from run_pipeline_and_extract_metrics")
                break

            result = results[0]
            if isinstance(result["per_stream_fps"], (int, float)) and result["per_stream_fps"] >= self.fps_floor:
                if result["num_streams"] > best_config[0]:
                    print(f"best_config[0]: {best_config[0]}")
                    best_config = (mid, ai_streams, non_ai_streams, result["per_stream_fps"])
                low = mid + 1
            else:
                #if mid == high:
                #    break
                high = mid - 1 

       #return best_config, self.results
       print(f"best_config[3]: {best_config[3]}")
       return best_config