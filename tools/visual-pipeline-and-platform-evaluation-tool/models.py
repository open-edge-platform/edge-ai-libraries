import os
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class Model:
    name: str
    precision: str
    bin: Path
    xml: Path
    proc: Path = None
    task: str = None
    devices: list[str] = field(default_factory=lambda: ["CPU", "GPU", "NPU"])

class ModelManager:
    def __init__(self):
        self.models: list[Model] = []

    def postprocess_known_models(self, model: Model):
    
        match model.name:
            case "efficientnet-b0_INT8":
                model.name = "EfficientNet B0"
                model.devices = ["CPU", "GPU"]
                model.task = "CLASSIFICATION"
            case "mobilenet-v2-pytorch":
                model.name = "MobileNet V2 PyTorch"
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "CLASSIFICATION"
            case "resnet-50-tf_INT8":
                model.name = "ResNet 50 TensorFlow"
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "CLASSIFICATION"
            case "ssdlite_mobilenet_v2_INT8":
                model.name = "SSDLite MobileNet V2"
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "CLASSIFICATION"
            case "yolov10m":
                model.name = "YOLO v10m 640x640"
                model.devices = ["CPU", "GPU"]
                model.task = "DETECTION"
            case "yolov10s":
                model.name = "YOLO v10s 640x640"
                model.devices = ["CPU", "GPU"]
                model.task = "DETECTION"
            case "yolov5m-416_INT8":
                model.name = "YOLO v5m 416x416"
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "DETECTION"
            case "yolov5m-640_INT8":
                model.name = "YOLO v5m 640x640"
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "DETECTION"
            case "yolov5s-416_INT8":
                model.name = "YOLO v5s 416x416"
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "DETECTION"
            case _:
                # If the model is not known, we keep the name as is,
                # we are optimistic and assume the model is compatible
                # with all the devices,
                # and we set the task to UNKNOWN
                model.devices = ["CPU", "GPU", "NPU"]
                model.task = "UNKNOWN"
    
        return model

    def discover_models(self, model_directory):
        # Clear the existing models
        self.models.clear()

        for root, _, files in os.walk(model_directory):
            for file in files:
                if file.endswith('.xml'):

                    # Take the xml file as is
                    xml_path = Path(root) / file

                    # The bin file is expected to have 
                    # the same name as the xml file
                    # but with a .bin extension
                    bin_path = xml_path.with_suffix('.bin')

                    # Extract the model name and precision
                    # from the xml file path
                    parts = xml_path.parts
                    
                    # The folder name of the xml file parent
                    # might be the precision or the model name
                    candidate = parts[-2]
                    if candidate in ["FP32", "FP16", "INT8", "FP16-INT8", "FP32-INT8"]:
                        precision = candidate
                        name = parts[-3]
                    else:
                        precision = "UNKNOWN"
                        name = candidate

                    # if the precision "UNKNOWN", then
                    # the proc file might be in the same directory
                    # as the xml file
                    # Find all the json files in the 
                    # parent directory of the xml file
                    if precision == "UNKNOWN":
                        json_files = list(xml_path.parent.glob('*.json'))

                        # If there are multiple json files,
                        # we take the first one
                        if json_files:
                            proc_path = json_files[0]
                        else:
                            proc_path = None
                    
                    # Otherwise, the proc file might be in the 
                    # xml file grandparent directory
                    else:
                        json_files = list(xml_path.parent.parent.glob('*.json'))
                        if json_files:
                            proc_path = json_files[0]
                        else:
                            proc_path = None

                    # Create the model instance
                    model = Model(
                        name=name,
                        precision=precision,
                        bin=bin_path,
                        xml=xml_path,
                        proc=proc_path,
                    )

                    # Postprocess the model to set devices and task
                    model = self.postprocess_known_models(model)

                    # Add the model to the list
                    self.models.append(model)
