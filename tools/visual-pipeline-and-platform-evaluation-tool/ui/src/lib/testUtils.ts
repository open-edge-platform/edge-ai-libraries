import { setTestMetrics, clearTestMode } from "@/store/reducers/metrics";
import { setTestDevices } from "@/store/reducers/devices";
import type { MetricData } from "@/store/reducers/metrics";
import type { Device } from "@/api/api.generated";
import type { AppDispatch } from "@/store";

let testIntervalId: ReturnType<typeof setInterval> | null = null;

const generateGpuMetrics = (gpuCount: number): MetricData[] => {
  const metrics: MetricData[] = [];

  // FPS metric
  metrics.push({
    name: "fps",
    fields: { value: 30 + Math.random() * 30 },
  });

  // CPU metric
  metrics.push({
    name: "cpu",
    fields: { usage_user: 45 + Math.random() * 20 },
  });

  // GPU metrics for each GPU
  for (let i = 0; i < gpuCount; i++) {
    const usage = 30 + Math.random() * 60; // Random usage between 30-90%

    ["compute", "render", "ccs"].forEach((engine) => {
      metrics.push({
        name: "gpu_engine_usage",
        fields: { usage: engine === "compute" ? usage : usage * 0.8 },
        tags: {
          gpu_id: i.toString(),
          engine: engine,
        },
      });
    });
  }

  return metrics;
};


// Simulates metrics for multiple GPUs
export const simulateMultipleGPUs = (
  dispatch: AppDispatch,
  gpuCount: number = 3,
) => {
  if (testIntervalId) {
    clearInterval(testIntervalId);
  }

  const mockDevices: Device[] = [];
  for (let i = 0; i < gpuCount; i++) {
    mockDevices.push({
      device_name: `GPU.${i}`,
      device_family: "GPU",
      full_device_name: `Intel® Arc™ A770 Graphics ${i}`,
      device_type: "DISCRETE",
      gpu_id: i,
    });
  }

  dispatch(setTestDevices(mockDevices));

  const updateMetrics = () => {
    const metrics = generateGpuMetrics(gpuCount);
    dispatch(setTestMetrics(metrics));
  };

  updateMetrics();

  testIntervalId = setInterval(updateMetrics, 1000);

  console.log(
    `Simulated ${gpuCount} GPUs with live updating test data`,
    { deviceCount: gpuCount },
  );
};

export const clearTestData = (dispatch: AppDispatch) => {
  if (testIntervalId) {
    clearInterval(testIntervalId);
    testIntervalId = null;
  }

  dispatch(clearTestMode());
  dispatch(setTestDevices([]));
  
  console.log("Cleared test data");
};
