from dataclasses import dataclass
from enum import Enum
import logging

import openvino as ov

logger = logging.getLogger("device")


class DeviceType(Enum):
    DISCRETE = "DISCRETE"
    INTEGRATED = "INTEGRATED"


class DeviceFamily(Enum):
    CPU = "CPU"
    GPU = "GPU"
    NPU = "NPU"


@dataclass
class DeviceInfo:
    """
    Class to hold device information.
    Not every property is exposed in this class.
    The output of the device information is similar to the following:

    Device: CPU
        AVAILABLE_DEVICES: ['']
        RANGE_FOR_ASYNC_INFER_REQUESTS: (1, 1, 1)
        RANGE_FOR_STREAMS: (1, 22)
        EXECUTION_DEVICES: ['CPU']
        FULL_DEVICE_NAME: Intel(R) Core(TM) Ultra 7 155H
        OPTIMIZATION_CAPABILITIES: ['FP32', 'INT8', 'BIN', 'EXPORT_IMPORT']
        DEVICE_TYPE: Type.INTEGRATED
        DEVICE_ARCHITECTURE: intel64
        NUM_STREAMS: 1
        INFERENCE_NUM_THREADS: 0
        PERF_COUNT: False
        INFERENCE_PRECISION_HINT: <Type: 'float32'>
        PERFORMANCE_HINT: PerformanceMode.LATENCY
        EXECUTION_MODE_HINT: ExecutionMode.PERFORMANCE
        PERFORMANCE_HINT_NUM_REQUESTS: 0
        ENABLE_CPU_PINNING: True
        ENABLE_CPU_RESERVATION: False
        SCHEDULING_CORE_TYPE: SchedulingCoreType.ANY_CORE
        MODEL_DISTRIBUTION_POLICY: set()
        ENABLE_HYPER_THREADING: True
        DEVICE_ID:
        CPU_DENORMALS_OPTIMIZATION: False
        LOG_LEVEL: Level.NO
        CPU_SPARSE_WEIGHTS_DECOMPRESSION_RATE: 1.0
        DYNAMIC_QUANTIZATION_GROUP_SIZE: 32
        KV_CACHE_PRECISION: <Type: 'uint8_t'>
        KEY_CACHE_PRECISION: <Type: 'uint8_t'>
        VALUE_CACHE_PRECISION: <Type: 'uint8_t'>
        KEY_CACHE_GROUP_SIZE: 0
        VALUE_CACHE_GROUP_SIZE: 0

    Device: GPU
        AVAILABLE_DEVICES: ['0']
        RANGE_FOR_ASYNC_INFER_REQUESTS: (1, 2, 1)
        RANGE_FOR_STREAMS: (1, 2)
        OPTIMAL_BATCH_SIZE: 1
        MAX_BATCH_SIZE: 1
        DEVICE_ARCHITECTURE: GPU: vendor=0x8086 arch=v12.71.4
        FULL_DEVICE_NAME: Intel(R) Arc(TM) Graphics (iGPU)
        DEVICE_UUID: 8680557d080000000002000000000000
        DEVICE_LUID: 409a0000499a0000
        DEVICE_TYPE: Type.INTEGRATED
        DEVICE_GOPS: {<Type: 'float16'>: 9216.0, <Type: 'float32'>: 4608.0, <Type: 'int8_t'>: 18432.0, <Type: 'uint8_t'>: 18432.0}
        OPTIMIZATION_CAPABILITIES: ['FP32', 'BIN', 'FP16', 'INT8', 'EXPORT_IMPORT']
        GPU_DEVICE_TOTAL_MEM_SIZE: 30477434880
        GPU_UARCH_VERSION: 12.71.4
        GPU_EXECUTION_UNITS_COUNT: 128
        GPU_MEMORY_STATISTICS: {}
        PERF_COUNT: False
        MODEL_PRIORITY: Priority.MEDIUM
        GPU_HOST_TASK_PRIORITY: Priority.MEDIUM
        GPU_QUEUE_PRIORITY: Priority.MEDIUM
        GPU_QUEUE_THROTTLE: Priority.MEDIUM
        GPU_ENABLE_SDPA_OPTIMIZATION: True
        GPU_ENABLE_LOOP_UNROLLING: True
        GPU_DISABLE_WINOGRAD_CONVOLUTION: False
        CACHE_DIR:
        CACHE_MODE: CacheMode.OPTIMIZE_SPEED
        PERFORMANCE_HINT: PerformanceMode.LATENCY
        EXECUTION_MODE_HINT: ExecutionMode.PERFORMANCE
        COMPILATION_NUM_THREADS: 22
        NUM_STREAMS: 1
        PERFORMANCE_HINT_NUM_REQUESTS: 0
        INFERENCE_PRECISION_HINT: <Type: 'float16'>
        ENABLE_CPU_PINNING: False
        ENABLE_CPU_RESERVATION: False
        DEVICE_ID: 0
        DYNAMIC_QUANTIZATION_GROUP_SIZE: 0
        ACTIVATIONS_SCALE_FACTOR: -1.0
        WEIGHTS_PATH:
        CACHE_ENCRYPTION_CALLBACKS: UNSUPPORTED TYPE
        KV_CACHE_PRECISION: <Type: 'dynamic'>
        MODEL_PTR: UNSUPPORTED TYPE

    Device: NPU
        AVAILABLE_DEVICES: ['3720']
        CACHE_DIR:
        COMPILATION_NUM_THREADS: 22
        DEVICE_ARCHITECTURE: 3720
        DEVICE_GOPS: {<Type: 'bfloat16'>: 0.0, <Type: 'float16'>: 4300.7998046875, <Type: 'float32'>: 0.0, <Type: 'int8_t'>: 8601.599609375, <Type: 'uint8_t'>: 8601.599609375}
        DEVICE_ID:
        DEVICE_PCI_INFO: {domain: 0 bus: 0 device: 0xb function: 0}
        DEVICE_TYPE: Type.INTEGRATED
        DEVICE_UUID: 80d1d11eb73811eab3de0242ac130004
        ENABLE_CPU_PINNING: False
        EXECUTION_DEVICES: NPU
        EXECUTION_MODE_HINT: ExecutionMode.PERFORMANCE
        FULL_DEVICE_NAME: Intel(R) AI Boost
        INFERENCE_PRECISION_HINT: <Type: 'float16'>
        LOG_LEVEL: Level.ERR
        MODEL_PRIORITY: Priority.MEDIUM
        NPU_BYPASS_UMD_CACHING: False
        NPU_COMPILATION_MODE_PARAMS:
        NPU_COMPILER_VERSION: 393219
        NPU_DEFER_WEIGHTS_LOAD: False
        NPU_DEVICE_ALLOC_MEM_SIZE: 0
        NPU_DEVICE_TOTAL_MEM_SIZE: 32924782592
        NPU_DRIVER_VERSION: 1738334590
        NPU_MAX_TILES: 2
        NPU_TILES: -1
        NPU_TURBO: False
        NUM_STREAMS: 1
        OPTIMAL_NUMBER_OF_INFER_REQUESTS: 1
        OPTIMIZATION_CAPABILITIES: ['FP16', 'INT8', 'EXPORT_IMPORT']
        PERFORMANCE_HINT: PerformanceMode.LATENCY
        PERFORMANCE_HINT_NUM_REQUESTS: 1
        PERF_COUNT: False
        RANGE_FOR_ASYNC_INFER_REQUESTS: (1, 10, 1)
        RANGE_FOR_STREAMS: (1, 4)
        WEIGHTS_PATH:
        WORKLOAD_TYPE: WorkloadType.DEFAULT
    """

    device_name: str
    full_device_name: str = ""
    device_type: "DeviceType" = DeviceType.INTEGRATED
    device_family: "DeviceFamily" = DeviceFamily.CPU
    gpu_id: int | None = None


class DeviceDiscovery:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DeviceDiscovery, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize OpenVINO Runtime Core and fetch available devices."""
        if not hasattr(self, "core"):
            self.core = ov.Core()
            self.devices = []
            for device in self.core.available_devices:
                full_device_name = str(
                    self.core.get_property(device, "FULL_DEVICE_NAME")
                )
                device_type = self.parse_device_type(device)
                device_family = self.parse_device_family(device)
                gpu_id = self.parse_gpu_id(device)
                self.devices.append(
                    DeviceInfo(
                        device_name=device,
                        full_device_name=full_device_name,
                        device_type=device_type,
                        device_family=device_family,
                        gpu_id=gpu_id,
                    )
                )

            # Add "GPU.<gpu_id>" to full_device_name if there are multiple GPUs
            gpu_devices = [
                d for d in self.devices if d.device_family == DeviceFamily.GPU
            ]
            if len(gpu_devices) > 1:
                for d in gpu_devices:
                    d.full_device_name += f" ({d.device_name})"

    def parse_device_type(self, device: str) -> DeviceType:
        type_str = str(self.core.get_property(device, "DEVICE_TYPE"))
        # type_str is expected to be "Type.INTEGRATED" or "Type.DISCRETE"
        if type_str == "Type.INTEGRATED":
            return DeviceType.INTEGRATED
        elif type_str == "Type.DISCRETE":
            return DeviceType.DISCRETE
        else:
            logger.error(
                f"Unknown device type: {type_str} for device: {device}. Fallback to INTEGRATED."
            )
            return DeviceType.INTEGRATED

    @staticmethod
    def parse_device_family(device: str) -> DeviceFamily:
        if device.startswith("CPU"):
            return DeviceFamily.CPU
        elif device.startswith("GPU"):
            return DeviceFamily.GPU
        elif device.startswith("NPU"):
            return DeviceFamily.NPU
        else:
            logger.error(
                f"Unknown device family for device: {device}. Fallback to CPU."
            )
            return DeviceFamily.CPU

    @staticmethod
    def parse_gpu_id(device: str) -> int | None:
        if device == "GPU":
            return 0
        elif device.startswith("GPU."):
            parts = device.split(".")
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
            else:
                logger.info(f"Incorrect gpu_id for device: {device}")
                return None
        else:
            return None

    def list_devices(self):
        """List all available devices."""
        return self.devices
