import subprocess
import time
from typing import List, Dict, Tuple
import re
import tempfile
from pipeline import SmartNVRPipeline, Transportation2Pipeline

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

   def evaluate_cmds(self, cmds: List[str]) -> float:
    
       for cmd in cmds:
           print("Generated command:")
           print(cmd)
           try:
               safe_cmd = cmd.replace('(', '\\(').replace(')', '\\)')
               wrapped_cmd = f'sh -c "{safe_cmd}"'
               print(f"wrapped_cmd: {wrapped_cmd}")
               with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as tmp_script:
                   tmp_script.write(wrapped_cmd)
                   tmp_script_path = tmp_script.name                  
               proc = subprocess.Popen(f"bash {tmp_script_path}", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
               out, err = proc.communicate(timeout=300)
           except subprocess.TimeoutExpired:
               proc.kill()
               out, err = proc.communicate()
               print(f"Gstreamer command timed out.")
           print("stdout", out)
           print("stder", err) 
           # Extract FPS from gst-launch output (this is a simple regex you can improve if needed)
           match_streams = re.search(r'number-streams=(\d+)', out)
           expected_streams = int(match_streams.group(1)) if match_streams else None
           # Try to extract fps from 'overall' that matches stream count
           fps_overall_matches = re.findall(r'FpsCounter\((overall|last).*?\):.*?number-streams=(\d+),\s+per-stream=([0-9]+\.[0-9]+)\s+fps', out)
           for mode, num_streams, fps in fps_overall_matches:
                if mode == "overall" and int(num_streams) == expected_streams:
                    print(f"Matched overall FPS: {fps}")
                    return float(fps)
       # Fallback: try to extract last reported FPS
           for mode, num_streams, fps in fps_overall_matches:
                if mode == "last" and int(num_streams) == expected_streams:
                    print(f"Fallback last FPS: {fps}")
                    return float(fps)
       print("No FPS match found")
       return 0.0
   def run(self) -> Tuple[int, int, int, float]:
       start_time = time.time()
       streams = 1
       last_good_config = (0, 0, 0, 0.0)
      
       # Phase 1: Exponential Expansion
       while True:
           if time.time() - start_time > 300:
               print("Time limit reached during exponential phase")
               break
           #ai_streams = max(1, int(streams * 0.2)) if self.model_type == "smartnvr" else streams
           #non_ai_streams = streams - ai_streams if self.model_type == "smartnvr" else 0
           ai_streams = max(1, int(streams * 0.2))
           non_ai_streams = streams - ai_streams
        #    parameters = {
        #        "object_detection_device": "CPU",
        #        "OBJECT_DETECTION_MODEL_PATH": "yolov5s.xml",
        #        "OBJECT_DETECTION_MODEL_PROC": "yolo-v5.json"
        #    }
        #    constants = {
        #        "VIDEO_PATH": self.video_path,
        #        "VIDEO_OUTPUT_PATH": "output_file.mp4"
        #    }
           #pipeline = self.pipeline_cls()
           cmds = self.pipeline_cls.evaluate(self.constants, self.parameters, non_ai_streams, ai_streams, self.elements)
           print(f"Generated commands: {cmds}")
           if isinstance(cmds, str):
               cmds = [cmds]
               
           fps = self.evaluate_cmds(cmds)
           self.results.append((streams, ai_streams, non_ai_streams, fps))
           if fps >= self.fps_floor:
                last_good_config = (streams, ai_streams, non_ai_streams, fps)
                streams *= 2  # Exponential doubling
           else:
                failed_streams = streams
                break
               
       # Phase 2: Binary Search 
       low = last_good_config[0] + 1
       high = failed_streams
       best_config = last_good_config

       while low <= high:
            if time.time() - start_time > 300:
                print("Time limit reached during linear phase.")
                break
            print(f"best_config[0]: {best_config[0]}")
            mid = (low + high)//2
            #ai_streams = max(1, int(mid * 0.2)) if self.model_type == "smartnvr" else mid
            #non_ai_streams = mid - ai_streams if self.model_type == "smartnvr" else 0
            ai_streams = max(1, int(streams * 0.2))
            non_ai_streams = streams - ai_streams

            #pipeline = self.pipeline_cls()
            cmds = self.pipeline_cls.evaluate(self.constants, self.parameters, non_ai_streams, ai_streams, self.elements)
            if isinstance(cmds, str):
                cmds = [cmds]

            fps = self.evaluate_cmds(cmds)
            self.results.append((mid, ai_streams, non_ai_streams, fps))

            if fps >= self.fps_floor:
                if fps > best_config[3]:
                    print(f"best_config[3]: {best_config[3]}")
                    best_config = (mid, ai_streams, non_ai_streams, fps)
                low = mid + 1
            else:
                high = mid - 1 

       #return best_config, self.results
       return best_config[3]
