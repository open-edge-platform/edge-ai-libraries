import argparse
import gi
import time
import logging
import sys

gi.require_version("Gst", "1.0")
from gi.repository import Gst

Gst.init()
logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

def scan_system():
    context = {"GPU": False,
               "NPU": False,
               "ie": False,
               "opencv": False,
               "va": False,
               "va-surface-sharing": False}
    return context

def sample_pipeline(pipeline, sample_duration):
    pipeline = Gst.parse_launch("!".join(pipeline))

    fps_counter = next(filter(lambda element: element.name == "gvafpscounter0", pipeline.children))

    bus = pipeline.get_bus()

    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(60)
    pipeline.set_state(Gst.State.NULL)
    time.sleep(5)

    while message := bus.pop():
        logger.info("Message: " + message)
    logger.info("FPS: " + fps_counter.get_property("avg-fps"))

    
def get_optimized_pipeline(pipeline, search_duration = 300, sample_duration = 10):
    pipeline = " ".join(pipeline).split("!")
    logger.info("Testing pipeline: " + "!".join(pipeline))
    sample_pipeline(pipeline, sample_duration)

def main():
    parser = argparse.ArgumentParser(
        prog="DL Streamer Pipeline Optimization Tool",
        description="Use this tool to try and find versions of your pipeline that will run with increased performance."
    )
    parser.add_argument("--search-duration", default=300,
                        help="Duration of time which should be spent searching for optimized pipelines (default: %(default)ss)")
    parser.add_argument("--sample-duration", default=10,
                        help="Duration of sampling individual pipelines. Longer duration should offer more stable results (default: %(default)ss)")
    parser.add_argument("pipeline", nargs="+",
                        help="Pipeline to be analyzed")
    args=parser.parse_args()

    get_optimized_pipeline(args.pipeline, args.search_duration, args.sample_duration)

if __name__ == "__main__":
    main()