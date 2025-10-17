import argparse
import time
import logging
import itertools
import os
import subprocess

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gst, GLib

####################################### Init ######################################################

Gst.init()
logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)
logger.info("GStreamer initialized successfully")
gst_version = Gst.version()
logger.info(f"GStreamer version: {gst_version.major}.{gst_version.minor}.{gst_version.micro}")


####################################### Utils #####################################################

def parse_element_parameters(element):
    parameters = element.strip().split(" ")
    del parameters[0]
    parsed_parameters = {}
    for parameter in parameters:
        parts = parameter.split("=")
        parsed_parameters[parts[0]] = parts[1]

    return parsed_parameters

def assemble_parameters(parameters):
    result = ""
    for parameter, value in parameters.items():
        result = result + parameter + "=" + value + " "

    return result

def log_parameters_of_interest(pipeline):
    for element in pipeline:
        if "gvadetect" in element:
            parameters = parse_element_parameters(element)
            logger.info(f'''Found Gvadetect, 
                device: {parameters.get("device", "not set")}, 
                batch size: {parameters.get("batch-size", "not set")}, 
                nireqs: {parameters.get("nireq", "not set")}''')
            
        if "gvaclassify" in element:
            parameters = parse_element_parameters(element)
            logger.info(f'''Found Gvaclassify, 
                device: {parameters.get("device", "not set")}, 
                batch size: {parameters.get("batch-size", "not set")}, 
                nireqs: {parameters.get("nireq", "not set")}''')

###################################### System Scanning ############################################

def scan_system():
    context = {"GPU": False,
               "NPU": False}

    # check for presence of GPU
    gpu_dir = "/dev/dri"
    files = os.listdir(gpu_dir)
    for file in files:
        if "render" in file:
            context["GPU"] = True

    if context["GPU"]:
        logger.info("Detected GPU Device")
    else:
        logger.info("No GPU Device detected")

    # check for presence of NPU
    npu_query = subprocess.run(["dpkg", "-l", "intel-driver-compiler-npu"], stderr=subprocess.DEVNULL)
    if npu_query.returncode == 0:
        context["NPU"] = True
        logger.info("Detected NPU Device")
    else:
        logger.info("No NPU Device detected")

    
    return context

##################################### Pipeline Running ############################################

def explore_pipelines(suggestions, base_fps, search_duration, sample_duration):
    best_pipeline = []
    start_time = time.time()
    best_fps = base_fps
    for combination in itertools.product(*suggestions):
        combination = list(combination)
        log_parameters_of_interest(combination)

        try:
            fps = sample_pipeline(combination, sample_duration)

            if fps > best_fps:
                best_fps = fps
                best_pipeline = combination

        except Exception as e:
            logger.debug(f"Pipeline failed to start: {e}")

        cur_time = time.time()
        if cur_time - start_time > search_duration:
            break

    return best_pipeline, best_fps

def sample_pipeline(pipeline, sample_duration):
    # check if there is an fps counter after the last inference element
    for i, element in enumerate(reversed(pipeline)):
        # exit early if one is found before other elements
        if "gvafpscounter" in element:
            break

        # add one if no counter was found before inference elements
        if "gvadetect" in element or "gvaclassify" in element:
            pipeline.insert(len(pipeline) - i, "gvafpscounter")

    pipeline = "!".join(pipeline)
    logger.debug(f"Testing: {pipeline}")


    pipeline = Gst.parse_launch(pipeline)

    logger.info(f"Sampling for {str(sample_duration)} seconds...")
    fps_counter = next(filter(lambda element: "gvafpscounter" in element.name, reversed(pipeline.children)))

    bus = pipeline.get_bus()

    pipeline.set_state(Gst.State.PLAYING)
    terminate = False
    start_time = time.time()
    while not terminate:
        time.sleep(1)

        # Incorrect pipelines sometimes get stuck in Ready state instead of failing.
        # Terminate in those cases.
        _, state, _ = pipeline.get_state(Gst.CLOCK_TIME_NONE)
        if state == Gst.State.READY:
            del pipeline
            raise RuntimeError("Pipeline not healthy, terminating early")

        cur_time = time.time()
        if cur_time - start_time > sample_duration:
            terminate = True

    pipeline.set_state(Gst.State.NULL)

    # Process any messages from the bus
    message = bus.pop()
    while message is not None:
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            logger.error(f"Pipeline error: {error.message}")
        elif message.type == Gst.MessageType.WARNING:
            warning, debug = message.parse_warning()
            logger.warning(f"Pipeline warning: {warning.message}")
        elif message.type == Gst.MessageType.STATE_CHANGED:
            old, new, pending = message.parse_state_changed()
            logger.debug(f"State changed: {old} -> {new}")
        else:
            logger.error(f"Other message: {str(message)}")
        message = bus.pop()

    del pipeline
    fps = fps_counter.get_property("avg-fps")
    logger.debug(f"Sampled fps: {fps}")
    return fps

######################################## Preprocess ###############################################

def preprocess_pipeline(pipeline):
    for element in pipeline:
        if "decodebin" in element:
            element = "decodebin3"
        
        if "vaapipostproc" in element:
            element = "vapostproc"

        if "vaapi-surface-sharing" in element:
            element = "va-surface-sharing"

    return pipeline

#################################### Gvadetect & Gvaclassify ######################################

def add_gvadetect_suggestions(suggestions, context):
    add_classification_suggestions("gvadetect", suggestions, context)

def add_gvaclassify_suggestions(suggestions, context):
    add_classification_suggestions("gvaclassify", suggestions, context)

def add_classification_suggestions(element, suggestions, context):
    if context["GPU"]:
        add_parameter_suggestions(element, "GPU", "va-surface-sharing", suggestions)

    if context["NPU"]:
        add_parameter_suggestions(element, "NPU", "va", suggestions)

    add_parameter_suggestions(element, "CPU", "opencv", suggestions)


def add_parameter_suggestions(element, device, backend, suggestions):
    batches = [1, 2, 4, 8, 16, 32]
    nireqs = range(1, 9)
    for suggestion in suggestions:
        if element in suggestion[0]:
            parameters = parse_element_parameters(suggestion[0])

            for batch in batches:
                for nireq in nireqs:
                    parameters["device"] = device
                    parameters["pre-process-backend"] = backend
                    parameters["batch-size"] = str(batch)
                    parameters["nireq"] = str(nireq)
                    suggestion.append(f"{element} {assemble_parameters(parameters)}")


####################################### Main Logic ################################################

def get_optimized_pipeline(pipeline, search_duration = 300, sample_duration = 10):
    context = scan_system()

    pipeline = " ".join(pipeline).split("!")

    try:
        fps = sample_pipeline(pipeline, sample_duration)
    except Exception as e:
        logger.error(f"Pipeline failed to start, unable to measure fps: {e}")
        raise RuntimeError("Provided pipeline is not valid")
        
    logger.info(f"FPS: {fps:.2f}")
    
    pipeline = preprocess_pipeline(pipeline)

    # Suggestions structure:
    #   [
    #       ["element1 param1=value1", "element1 param1=value2", ...other variants],
    #       ["element2 param1=value1", "element2 param1=value2", ...other variants],
    #       ["element3 param1=value1", "element3 param1=value2", ...other variants],
    #       ...other pipeline elements
    #   ]
    suggestions = []
    for element in pipeline:
        suggestions.append([element])

    add_gvadetect_suggestions(suggestions, context)
    add_gvaclassify_suggestions(suggestions, context)
    best_pipeline, best_fps = explore_pipelines(suggestions, fps, search_duration, sample_duration)
    
    if best_pipeline == []:
       best_pipeline = pipeline
       best_fps = fps

    return "!".join(best_pipeline), best_fps

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

    try:
        best_pipeline, best_fps = get_optimized_pipeline(args.pipeline, args.search_duration, args.sample_duration)
        logger.info(f"Best found pipeline: {best_pipeline} with fps: {best_fps}")
    except Exception as e:
        logger.error(f"Failed to optimize pipeline: {e}")

if __name__ == "__main__":
    main()
