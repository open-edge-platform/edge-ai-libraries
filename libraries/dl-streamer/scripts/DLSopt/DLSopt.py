import argparse
import gi
import time
import logging
import itertools

gi.require_version("Gst", "1.0")
from gi.repository import Gst

#################################################### Init ###############################################################################

Gst.init()
logging.basicConfig(level=logging.DEBUG, format="[%(name)s] [%(levelname)8s] - %(message)s")
logger = logging.getLogger(__name__)

########################################################## Utils #####################################################################

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

#################################################### System Scanning ####################################################################

def scan_system():
    context = {"GPU": False,
               "NPU": False,
               "ie": False,
               "opencv": False,
               "va": False,
               "va-surface-sharing": False}
    return context

##################################################### Pipeline Running ###################################################################

def explore_pipelines(suggestions, base_fps, search_duration, sample_duration):
    best_pipeline = []
    start_time = time.time()
    best_fps = base_fps
    for combination in itertools.product(*suggestions):
        fps = sample_pipeline(list(combination), sample_duration)

        if fps > best_fps:
            best_fps = fps
            best_pipeline = list(combination)

        cur_time = time.time()
        if cur_time - start_time > search_duration:
            break

    return best_pipeline

def sample_pipeline(pipeline, sample_duration):
    pipeline = "!".join(pipeline)
    logger.debug("Testing: " + pipeline)

    pipeline = Gst.parse_launch(pipeline)

    try:
        fps_counter = next(filter(lambda element: "gvafpscounter" in element.name, pipeline.children))

        bus = pipeline.get_bus()

        pipeline.set_state(Gst.State.PLAYING)
        time.sleep(sample_duration)
        pipeline.set_state(Gst.State.NULL)

        while message := bus.pop():
            logger.info("Message: " + message)
    
        fps = fps_counter.get_proprty("avg-fps")
        del pipeline
        return fps
    except StopIteration:
        logger.error("Pipeline is missing a gvafpscounter!")
        del pipeline
        return 0
    except AttributeError:
        logger.error("Could not find the `avg-fps` property on Gvafpscounter!")
        del pipeline
        return 0

########################################################## Gvadetect #####################################################################

def add_gvadetect_suggestions(suggestions, context):
    devices = ["CPU"]
    backends = [""]
    batches = range(32)
    nireqs = range(8)

    if context["GPU"]:
        devices.append("GPU")

    if context["NPU"]:
        devices.append("NPU")

    if context["ie"]:
        backends.append("ie")
    
    if context["opencv"]:
        backends.append("opencv")

    if context["va"]:
        backends.append("va")

    if context["va-surface-sharing"]:
        backends.append("va-surface-sharing")

    for suggestion in suggestions:
        if " gvadetect" in suggestion[0]:
            parameters = parse_element_parameters(suggestion[0])

            for device in devices:
                for backend in backends:
                    for batch in batches:
                        for nireq in nireqs:
                            parameters["device"] = device
                            parameters["pre-process-backend"] = backend
                            parameters["batch-size"] = str(batch + 1)
                            parameters["nireq"] = str(nireq + 1)
                            suggestion.append("gvadetect " + assemble_parameters(parameters))

########################################################## Gvaclassify #####################################################################

def add_gvaclassify_suggestions(suggestions, context):
    devices = ["CPU"]
    backends = [""]
    batches = range(32)
    nireqs = range(8)

    if context["GPU"]:
        devices.append("GPU")

    if context["NPU"]:
        devices.append("NPU")

    if context["ie"]:
        backends.append("ie")
    
    if context["opencv"]:
        backends.append("opencv")

    if context["va"]:
        backends.append("va")

    if context["va-surface-sharing"]:
        backends.append("va-surface-sharing")

    for suggestion in suggestions:
        if " gvaclassify" in suggestion[0]:
            parameters = parse_element_parameters(suggestion[0])

            for device in devices:
                for backend in backends:
                    for batch in batches:
                        for nireq in nireqs:
                            parameters["device"] = device
                            parameters["pre-process-backend"] = backend
                            parameters["batch-size"] = str(batch + 1)
                            parameters["nireq"] = str(nireq + 1)
                            suggestion.append("gvaclassify " + assemble_parameters(parameters))

########################################################## Main Logic #####################################################################

def get_optimized_pipeline(pipeline, search_duration = 300, sample_duration = 10):
    context = scan_system()

    pipeline = " ".join(pipeline).split("!")
    fps = sample_pipeline(pipeline, sample_duration)
    logger.info("FPS: " + str(fps))
    
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
    best_pipeline = explore_pipelines(suggestions, fps, search_duration, sample_duration)
    
    if best_pipeline == []:
        best_pipeline = pipeline

    return pipeline

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
