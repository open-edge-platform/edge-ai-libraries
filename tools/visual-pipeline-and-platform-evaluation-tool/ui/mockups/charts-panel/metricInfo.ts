// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ChartId } from "./chartCatalog";
import { average } from "./fakeMetrics";
import type { DeviceStats } from "./devices";

export type Tone = "good" | "warn" | "bad" | "neutral";
export type Reading = { tone: Tone; text: string };

export type TileId = "fps" | "latency" | "cpu" | "gpu" | "npu" | "memory";

export type MetricHelp = {
  title: string;
  what: string;
  scale?: string;
  read: (s: DeviceStats) => Reading;
};

export const TONE_COLOR: Record<Tone, string> = {
  good: "var(--color-success)",
  warn: "var(--color-yellow-chart)",
  bad: "var(--color-destructive)",
  neutral: "var(--color-muted-foreground)",
};

const LOAD_SCALE = "Normal < 70% · High 70–85% · Critical ≥ 85%";

const ENGINE_ADVICE: Record<string, string> = {
  Compute:
    "inference is GPU-bound — try a smaller or INT8 model, or move a model to NPU.",
  Render:
    "inference is GPU-bound — try a smaller or INT8 model, or move a model to NPU.",
  Video:
    "decoding/encoding is the limit — fewer streams or lower input resolution will help.",
  VE: "scaling and color conversion (vapostproc) is the limit — reduce resizing or resolution.",
  Copy: "frames are copied between memories — keep them in VAMemory end-to-end.",
};

export const TILE_HELP: Record<TileId, MetricHelp> = {
  fps: {
    title: "Frame rate",
    what: "Frames per second processed by the pipeline, per stream. For real-time processing it should stay close to the input video's frame rate (e.g. 30 fps).",
    read: (s) => {
      const recent = average(s.fps.series.slice(-10));
      const run = average(s.fps.series);
      if (recent < run * 0.9) {
        return {
          tone: "warn",
          text: `Dropping: last 10 s average ${recent.toFixed(1)} fps vs. ${run.toFixed(1)} fps for the run. A device has probably saturated — check the GPU and CPU tiles.`,
        };
      }
      if ((s.fps.max - s.fps.min) / Math.max(run, 1) > 0.25) {
        return {
          tone: "warn",
          text: "Unstable: frame rate varies a lot. Frames are processed in bursts, often because a queue fills and drains.",
        };
      }
      return {
        tone: "good",
        text: "Stable: the pipeline keeps up with its input at a steady rate.",
      };
    },
  },
  latency: {
    title: "Latency",
    what: "Time a single frame spends in the pipeline: from the source element's output until it is pushed into the sink. It is independent of FPS — high FPS can still mean high latency when frames wait in queues.",
    read: (s) => {
      const peakRatio = s.latencyMax.max / Math.max(s.latency.value, 1);
      if (s.latency.value > 100) {
        return {
          tone: "bad",
          text: `High: ${s.latency.value.toFixed(0)} ms per frame is noticeable for live use (alerts, tracking).`,
        };
      }
      if (peakRatio > 1.5) {
        return {
          tone: "warn",
          text: `Spiky: average ${s.latency.value.toFixed(0)} ms but up to ${s.latencyMax.max.toFixed(0)} ms. Some frames stall — check queue sizes and the busiest device.`,
        };
      }
      return {
        tone: "good",
        text: "Low and steady: frames move through the pipeline without waiting.",
      };
    },
  },
  cpu: {
    title: "CPU",
    what: "Share of time all CPU cores spend running user code (decoding, pre/post-processing, inference on CPU). Also shows the average core frequency and package temperature.",
    scale: LOAD_SCALE,
    read: (s) => {
      const hot =
        s.cpuTemp.value >= 85
          ? ` Temperature ${s.cpuTemp.value.toFixed(0)} °C may throttle the frequency.`
          : "";
      if (s.cpu.value >= 85) {
        return {
          tone: "bad",
          text: `Saturated: CPU is likely limiting FPS. Move decoding to GPU (vah264dec) or inference to GPU/NPU.${hot}`,
        };
      }
      if (s.cpu.value >= 70) {
        return {
          tone: "warn",
          text: `Busy: little headroom left for more streams.${hot}`,
        };
      }
      return {
        tone: hot ? "warn" : "good",
        text: `Headroom available: CPU is not the bottleneck.${hot}`,
      };
    },
  },
  gpu: {
    title: "GPU",
    what: "Load of the busiest GPU engine. Compute/Render run inference, Video decodes/encodes, Video Enhance scales and converts colors, Copy moves memory. A GPU is as fast as its most loaded engine.",
    scale: LOAD_SCALE,
    read: (s) => {
      const top = [...s.engines].sort((a, b) => b.value - a.value)[0];
      const advice = ENGINE_ADVICE[top.label] ?? "";
      if (s.gpu.value >= 85) {
        return {
          tone: "bad",
          text: `${top.label} engine saturated (${top.value.toFixed(0)}%) — likely bottleneck: ${advice}`,
        };
      }
      if (s.gpu.value >= 70) {
        return {
          tone: "warn",
          text: `${top.label} engine busy (${top.value.toFixed(0)}%): ${advice}`,
        };
      }
      return {
        tone: "good",
        text: `Headroom available: busiest engine is ${top.label} at ${top.value.toFixed(0)}%.`,
      };
    },
  },
  npu: {
    title: "NPU",
    what: "Load of the Neural Processing Unit, a low-power AI accelerator. Models run here only when their device is set to NPU.",
    scale: LOAD_SCALE,
    read: (s) => {
      if (s.npu.value < 5) {
        return {
          tone: "neutral",
          text: "Idle: no model runs on NPU. It is free capacity, e.g. for a classification model.",
        };
      }
      if (s.npu.value >= 85) {
        return {
          tone: "bad",
          text: "Saturated: the NPU model limits FPS. Use a smaller model or split work with GPU.",
        };
      }
      if (s.npu.value >= 70) {
        return { tone: "warn", text: "Busy: little headroom left." };
      }
      return {
        tone: "good",
        text: "Working with headroom; offloading here keeps GPU and CPU free.",
      };
    },
  },
  memory: {
    title: "Memory",
    what: "System RAM in use. It is system-wide, so it includes other processes, not only this pipeline.",
    scale: LOAD_SCALE,
    read: (s) => {
      const growth = s.memory.series.at(-1)! - s.memory.series[0];
      if (s.memory.value >= 85) {
        return {
          tone: "bad",
          text: "Almost full: risk of swapping or out-of-memory. Run fewer streams or smaller models.",
        };
      }
      if (growth > 5) {
        return {
          tone: "warn",
          text: `Growing: +${growth.toFixed(1)} pp during the run. Keep an eye on it for long runs.`,
        };
      }
      return {
        tone: "good",
        text: "Stable with free memory available.",
      };
    },
  },
};

type HelpItem = { label: string; description: string };

export const CHART_HELP: Record<ChartId, HelpItem[]> = {
  fps: [
    {
      label: "Frame Rate",
      description:
        "Frames per second per stream. Flat line = stable throughput; dips show moments when a device could not keep up.",
    },
  ],
  latency: [
    {
      label: "Avg",
      description:
        "Mean time per frame from the source element's output to the push into the sink.",
    },
    {
      label: "Min / Max",
      description:
        "Fastest and slowest frame in each sample. A Max far above Avg means occasional stalls.",
    },
  ],
  utilization: [
    { label: "CPU", description: "User time of all CPU cores." },
    { label: "GPU", description: "Busiest GPU engine of the selected GPU." },
    { label: "NPU", description: "NPU load." },
    {
      label: "Memory",
      description: "System RAM in use. The highest line is the first suspect.",
    },
  ],
  power: [
    { label: "GPU", description: "Power drawn by the selected GPU." },
    {
      label: "Package",
      description: "Power of the whole processor package.",
    },
    { label: "NPU", description: "Power drawn by the NPU." },
  ],
  cpuUsage: [
    {
      label: "CPU Usage",
      description:
        "User time of all cores. Sustained > 85% usually limits FPS.",
    },
  ],
  cpuFreq: [
    {
      label: "Frequency",
      description:
        "Average core frequency. A drop under load often means thermal or power throttling.",
    },
  ],
  cpuTemp: [
    {
      label: "Temperature",
      description:
        "CPU package temperature. Around 85 °C and above the CPU may lower its frequency.",
    },
  ],
  memory: [
    {
      label: "Memory",
      description:
        "System RAM in use. A steadily rising line can indicate a leak in long runs.",
    },
  ],
  gpuEngines: [
    { label: "Compute / Render", description: "Inference (OpenVINO on GPU)." },
    { label: "Video", description: "Hardware decode and encode." },
    {
      label: "Video Enhance",
      description: "Scaling and color conversion (vapostproc).",
    },
    { label: "Copy", description: "Memory copies between buffers." },
  ],
  gpuFreq: [
    {
      label: "Frequency",
      description:
        "GPU clock. It rises with load; a drop while busy can mean power or thermal limits.",
    },
  ],
  gpuPower: [
    { label: "GPU Power", description: "Power drawn by the GPU." },
    {
      label: "Package Power",
      description: "Power of the whole processor package.",
    },
  ],
  npuUsage: [
    {
      label: "NPU Usage",
      description: "NPU load. Near 0% means no model is assigned to NPU.",
    },
  ],
  npuPower: [{ label: "NPU Power", description: "Power drawn by the NPU." }],
  npuFreq: [
    {
      label: "NPU Frequency",
      description: "NPU clock; it rises when a model runs on the NPU.",
    },
  ],
};
